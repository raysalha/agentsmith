import asyncio
from contextlib import AsyncExitStack
import os
import re
import subprocess
import time
from typing import Any, Optional
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from agent_mbpp.system_prompt import build_system_prompt_mbpp
from agent_mbpp.system_prompt import build_user_prompt_mbpp
from agent_swebench.system_prompt import build_system_prompt_swe
from agent_swebench.system_prompt import build_user_prompt_swe
from helper.data_models import MBPPTaskInput, SWEBenchTaskInput, SandboxConfig
from helper.data_models import SolutionOutput, StepMetrics
from helper.misc import MAX_TURN_ERROR, MBPP_MAX_TURN, MORE_THAN_ONE_CODE_BLOCK
from helper.misc import RED, RESET, SWEBENCH_MAX_TURN, YELLOW, SAFETY_MSG
from helper.misc import NO_CODE_BLOCK
from helper.sandbox import Sandbox

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API")

SAFETY_STATUS_RESPONSE = re.compile(
    r"\s*user\s+safety\s*:\s*\w+\s*response\s+safety\s*:\s*\w+\s*",
    re.IGNORECASE,
)
MAX_REQUEST_RETRIES = 3
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


def is_safety_status_response(message: str) -> bool:
    """Return whether a provider returned metadata instead of an answer."""
    return bool(SAFETY_STATUS_RESPONSE.fullmatch(message))


def token_counts(response: Any) -> tuple[int, int]:
    """Return provider-reported input and output tokens, if available."""
    usage = getattr(response, "usage", None)
    return (
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    return (isinstance(error, APIStatusError) and error.status_code
            in RETRYABLE_STATUS_CODES)


class Orchestrator:
    def __init__(self, model: str, url: str, target: str,
                 sandbox_conf: SandboxConfig, eval_script: Optional[str]):
        self.exit_stack = AsyncExitStack()
        self.sandbox = Sandbox(sandbox_conf, target, eval_script)
        self.model = model
        self.llm = OpenAI(
            api_key=API_KEY,
            base_url=url,
            max_retries=0,
        )

    async def create_completion(self, messages: Any
                                ) -> tuple[Any, float, int]:
        """Create a completion, retrying transient provider failures."""
        started = time.perf_counter()
        retries = 0

        while True:
            try:
                response = self.llm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                return (response,
                        round((time.perf_counter() - started) * 1_000, 2),
                        retries)
            except (APIConnectionError, APIStatusError,
                    APITimeoutError) as error:
                if (retries >= MAX_REQUEST_RETRIES
                        or not is_retryable_error(error)):
                    raise
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
            benchmark = "swebench"
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
        turns = MBPP_MAX_TURN if benchmark == "mbpp" else SWEBENCH_MAX_TURN
        for i in range(turns):
            message = ""
            sandbox_input = ""
            sandbox_output = ""
            observation = ""
            print(f"\nTURN: ({i+1}/{turns}):")

            response, time_ms, retries = await self.create_completion(messages)
            total_requests += retries + 1

            input_tokens, output_tokens = token_counts(response)
            message = response.choices[0].message.content
            llm_output = message if message else ""
            print(llm_output)

            if is_safety_status_response(llm_output):
                messages.append({"role": "assistant", "content": llm_output})
                messages.append({"role": "user", "content": SAFETY_MSG})
            else:

                try:
                    matches = re.findall(r"```python\s*([\s\S]*?)```", llm_output)
                except Exception:
                    matches = []
    
                if len(matches) == 1:
                    sandbox_input = matches[0]
                    result = await self.sandbox.run(sandbox_input)
                    if result.final_answer:
                        success = True
                    observation = result.output
                    if result.error:
                        observation += f"{RED}ERROR: {result.error}{RESET}"
                elif len(matches) < 1:
                    observation = NO_CODE_BLOCK
                else:
                    observation = MORE_THAN_ONE_CODE_BLOCK

                sandbox_output = "Sandbox output:\n" + observation
                messages.append({"role": "assistant", "content": llm_output})
                messages.append({"role": "user", "content": sandbox_output})

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

        error = None
        if success is False:
            error = RED + MAX_TURN_ERROR + RESET

        solutio = result.final_answer if result and result.final_answer else ""
        task_id = str(task.task_id) if isinstance(
            task, MBPPTaskInput) else task.instance_id

        return SolutionOutput(
            task_id=task_id,
            benchmark=benchmark,
            success=success,
            solution=solutio,
            iterations=len(steps),
            total_requests=total_requests,
            total_input_tokens=sum(step.input_tokens for step in steps),
            total_output_tokens=sum(step.output_tokens for step in steps),
            total_time_seconds=round(time.perf_counter() - start, 2),
            steps=steps,
            system_prompt=system_prompt,
            error=error,
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
