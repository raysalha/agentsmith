import traceback
import asyncio
from contextlib import AsyncExitStack
import os
import re
import subprocess
import time
from typing import Any, Optional
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from helper.mbpp_prompts import build_system_prompt_mbpp
from helper.mbpp_prompts import build_user_prompt_mbpp
from helper.swe_prompts import build_system_prompt_swe, build_user_prompt_swe
from helper.data_models import MBPPTaskInput, SWEBenchTaskInput, SandboxConfig
from helper.data_models import SolutionOutput, StepMetrics
from helper.misc import MAX_TURN_ERROR, MBPP_MAX_TURN, MORE_THAN_ONE_CODE_BLOCK
from helper.misc import RED, RESET, SWEBENCH_MAX_TURN, YELLOW, SAFETY_MSG
from helper.misc import NO_CODE_BLOCK, EMPTY_LLM_RESPONSE, EMPTY_SANDBOX_OUTPUT
from helper.misc import NO_GITPATCH
from helper.models import get_model_candidates, pick_model
from helper.sandbox import Sandbox

load_dotenv()

API_KEYS = re.split(r"\s*,\s*", os.getenv("OPENROUTER_API", "").strip())
API_KEY = API_KEYS[0]

SAFETY_STATUS_RESPONSE = re.compile(
    r"user\s+safety\s*:\s*\w+.*"
    r"(?:response\s+safety\s*:\s*\w+)?",
    flags=re.IGNORECASE | re.DOTALL,
)
PYTHON_BLOCK = re.compile(r"```python\s*([\s\S]*?)```", re.IGNORECASE)
JSON_BLOCK = re.compile(r'"Python"\s*:\s*"((?:\\.|[^"\\])*)"', re.IGNORECASE)
MAX_REQUEST_RETRIES = 3
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


def is_safety_status_response(message: str) -> bool:
    """Return whether a provider returned metadata instead of an answer."""
    return bool(SAFETY_STATUS_RESPONSE.fullmatch(message.strip()))


def normalize_provider_wrappers(message: str) -> str:
    """Remove channel markers emitted by some OpenRouter models."""
    return re.sub(r"<\|/?channel\|?>", "", message,
                  flags=re.IGNORECASE).strip()


def response_protocol_error(message: str) -> str | None:
    """Return protocol feedback if a model response must not be executed."""
    message = normalize_provider_wrappers(message)
    if not message.strip():
        return EMPTY_LLM_RESPONSE
    if is_safety_status_response(message):
        return SAFETY_MSG

    matches_py = PYTHON_BLOCK.findall(message)
    matches_json = JSON_BLOCK.findall(message)
    if len(matches_py) + len(matches_json) == 0:
        return NO_CODE_BLOCK
    if len(matches_py) + len(matches_json) != 1:
        return MORE_THAN_ONE_CODE_BLOCK
    return None


def extract_python_code(message: str) -> str:
    message = normalize_provider_wrappers(message)
    match = PYTHON_BLOCK.findall(message)
    if not match:
        match = JSON_BLOCK.findall(message)
        if not match:
            raise ValueError("Cannot extract code from invalid agent response")
    return str(match[0])


def is_valid_patch(answer: str) -> bool:
    """Reject a false success when get_patch() returned an error string."""
    patch = answer.strip().lower()
    return (
        patch.startswith("diff --git ") and
        "no changes detected" not in patch
    )


def token_counts(response: Any) -> tuple[int, int]:
    """Return provider-reported input and output tokens, if available."""
    usage = getattr(response, "usage", None)
    return (
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def is_retryable(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    return (isinstance(error, APIStatusError) and error.status_code
            in RETRYABLE_STATUS_CODES)


class Orchestrator:
    def __init__(self, model: str, url: str, target: str,
                 sandbox_conf: SandboxConfig, eval_script: Optional[str]):
        self.exit_stack = AsyncExitStack()
        self.sandbox = Sandbox(sandbox_conf, target, eval_script)
        main_model = pick_model() if model in (None, "agentsmith") else model
        self.model_candidates = get_model_candidates(main_model)
        self.current_model_index = 0
        self.model = self.model_candidates[0]
        self.index = 0
        self.llm = OpenAI(
            api_key=API_KEY,
            base_url=url,
            max_retries=0,
        )

    def rotate_model(self) -> bool:
        if self.current_model_index + 1 < len(self.model_candidates):
            self.current_model_index += 1
            self.model = self.model_candidates[self.current_model_index]
            print("Switching to fallback model:", self.model)
            return True
        return False

    async def create_completion(self, messages: Any
                                ) -> tuple[Any, float, int]:
        """Create a completion, retrying transient provider failures."""
        started = time.perf_counter()
        retries = 0

        while True:
            try:
                print("Using:", self.model)
                response = self.llm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                return (response,
                        round((time.perf_counter() - started) * 1_000, 2),
                        retries)
            except (APIConnectionError, APITimeoutError):
                if retries >= MAX_REQUEST_RETRIES:
                    raise
                retries += 1
                await asyncio.sleep(min(2 ** (retries - 1), 8))
            except APIStatusError as e:
                if e.status_code == 429 and len(API_KEYS) > 1:
                    self.index = (self.index + 1) % len(API_KEYS)
                    print("Rate limit exceeded; switching API key")
                    self.llm.api_key = API_KEYS[self.index]
                elif self.rotate_model():
                    retries = 0
                    self.index = 0
                    self.llm.api_key = API_KEYS[self.index] if API_KEYS else ""
                    print("Rate limit or provider error; rotating model")
                elif retries >= MAX_REQUEST_RETRIES or not is_retryable(e):
                    raise
                else:
                    retries += 1
                    await asyncio.sleep(min(2 ** (retries - 1), 8))

    async def process_query(
        self,
        task: MBPPTaskInput | SWEBenchTaskInput,
        args: Any
    ) -> SolutionOutput:
        if isinstance(task, MBPPTaskInput):
            system_prompt = build_system_prompt_mbpp(self.sandbox)
            user_prompt = build_user_prompt_mbpp(task)
            benchmark = "mbpp"
        elif isinstance(task, SWEBenchTaskInput):
            system_prompt = build_system_prompt_swe(self.sandbox)
            user_prompt = build_user_prompt_swe(task)
            benchmark = "swe" + "bench"
        else:
            print("Error: unknown task type.")
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        steps = []
        success = False
        total_requests = 0
        start = time.perf_counter()
        result = None
        error = ""
        turns = MBPP_MAX_TURN if benchmark == "mbpp" else SWEBENCH_MAX_TURN
        try:
            for i in range(turns):
                llm_output = ""
                sandbox_input = ""
                sandbox_output = ""
                observation = ""
                print(f"\nTURN: ({i+1}/{turns}):")

                protocol_attempt = 0
                while True:
                    try:
                        lol = await self.create_completion(messages)
                        response, time_ms, retries = lol
                    except Exception:
                        if self.rotate_model():
                            protocol_attempt = 0
                            continue
                        raise
                    total_requests += retries + 1
                    input_tokens, output_tokens = token_counts(response)
                    llm_output = (response.choices[0].message.content
                                  if response.choices else "") or ""
                    protocol_error = response_protocol_error(llm_output)
                    if not protocol_error:
                        break
                    if protocol_attempt >= 1:
                        if self.rotate_model():
                            protocol_attempt = 0
                            continue
                        break
                    protocol_attempt += 1
                    messages.append({"role": "user",
                                    "content": protocol_error})
                print(llm_output)

                protocol_error = response_protocol_error(llm_output)
                if protocol_error:
                    observation = protocol_error
                    sandbox_output = "Sandbox output:\n" + observation
                    messages.append({"role": "assistant", "content":
                                    llm_output or "<empty response>"})
                    messages.append({"role": "user", "content":
                                    sandbox_output})
                else:
                    sandbox_input = extract_python_code(llm_output)
                    result = await self.sandbox.run(sandbox_input)
                    if result.final_answer:
                        if (benchmark != "mbpp" and not
                                is_valid_patch(result.final_answer)):
                            result.error = NO_GITPATCH
                            result.final_answer = None
                        else:
                            success = True
                    observation = result.output
                    if result.error:
                        observation += f"{RED}ERROR: {result.error}{RESET}"

                    if observation == "":
                        observation = EMPTY_SANDBOX_OUTPUT
                    sandbox_output = "Sandbox output:\n" + observation
                    messages.append({"role": "assistant", "content": llm_output
                                     })
                    messages.append({"role": "user", "content": sandbox_output
                                     })

                print(f"\n{YELLOW}SANDBOX:\n{observation}{RESET}")

                steps.append(StepMetrics(
                    step=i + 1,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_time_ms=time_ms,
                    api_url=args.provider_url,
                    model_name=response.model,
                    llm_output=llm_output,
                    sandbox_input=sandbox_input,
                    sandbox_output=sandbox_output,
                    retries=retries,
                ))
                if success:
                    break
        except Exception as e:
            print(e)
            traceback.print_exc()
            error = str(e)
        finally:
            if success is False and error == "":
                error = RED + MAX_TURN_ERROR + RESET

            sol = result.final_answer if result and result.final_answer else ""
            task_id = str(task.task_id) if isinstance(
                task, MBPPTaskInput) else task.instance_id

            return SolutionOutput(
                task_id=task_id,
                benchmark=benchmark,
                success=success,
                solution=sol,
                iterations=len(steps),
                total_requests=total_requests,
                total_input_tokens=sum(step.input_tokens for step in steps),
                total_output_tokens=sum(step.output_tokens for step in steps),
                total_time_seconds=round(time.perf_counter() - start, 2),
                steps=steps,
                system_prompt=system_prompt,
                error=error or "",
            )

    async def cleanup(self) -> None:
        """Clean up resources"""
        container_name = os.getenv("AGENT_DOCKER_CONTAINER")
        if container_name:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
        await self.sandbox.close()
        await self.exit_stack.aclose()
