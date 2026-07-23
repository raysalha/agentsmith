import argparse
import asyncio
import io
import tarfile
import time
import json
import os
import docker
import re
from typing import Any
from .misc import RED, GREEN, YELLOW, RESET, NO_CODE_BLOCK
from .misc import MORE_THAN_ONE_CODE_BLOCK, MBPP_MAX_TURN, MAX_TURN_ERROR
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from contextlib import AsyncExitStack
from .sandbox import Sandbox
from .data_models import MBPPTaskInput, SWEBenchTaskInput
from .data_models import SandboxConfig, SolutionOutput, StepMetrics
from .system_prompt import build_system_prompt, build_system_prompt_mbpp

load_dotenv()

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


def copy_to_container(container, src_path, dest_path):
    data = io.BytesIO()

    filename = os.path.basename(dest_path)

    with tarfile.open(fileobj=data, mode="w") as tar:
        info = tar.gettarinfo(src_path, arcname=filename)

        # Avoid host UID/GID leaking into container
        info.uid = 0
        info.gid = 0
        info.uname = "root"
        info.gname = "root"

        with open(src_path, "rb") as f:
            tar.addfile(info, f)

    data.seek(0)

    container.put_archive(
        path=os.path.dirname(dest_path),
        data=data.read()
    )


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    return (isinstance(error, APIStatusError) and error.status_code
            in RETRYABLE_STATUS_CODES)


class Orchestrator:
    def __init__(self, model: str, url: str, target: str):
        self.exit_stack = AsyncExitStack()
        self.model = model
        self.llm = OpenAI(
            api_key=os.getenv("OPENROUTER_API"),
            base_url=url,
            max_retries=0,
        )

        self.sandbox = Sandbox(SandboxConfig(), target)

    async def create_completion(self, messages: list[dict[str, str]]) -> tuple[Any, float, int]:
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

    async def process_query(self, query: str) -> str:
        """Process a query using OPENROUTER and MCP tools."""

        messages = [
            {"role": "system", "content": build_system_prompt(self.sandbox)},
            {"role": "user", "content": query},
        ]

        for i in range(MBPP_MAX_TURN):
            print(f"\nTURN: ({i+1}/{MBPP_MAX_TURN}):")

            response, _, _ = await self.create_completion(messages)

            message = response.choices[0].message.content
            print(message)

            if is_safety_status_response(message or ""):
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was provider safety metadata, not an agent "
                        "response. Do not output safety labels; follow the required Thought and "
                        "single Python code-block format."
                    ),
                })
                continue

            try:
                matches = re.findall(r"```python\s*([\s\S]*?)```",
                                     "" if message is None else message)
            except Exception:
                matches = []

            if len(matches) == 1:
                result = await self.sandbox.run(matches[0])
                if result.final_answer is not None:
                    return f"{GREEN}FINAL ANSWER: {result.final_answer}{RESET}"
                observation = result.output
                if result.error:
                    observation += f"{RED}ERROR: {result.error}{RESET}"

            elif len(matches) > 0:
                observation = MORE_THAN_ONE_CODE_BLOCK

            else:
                observation = NO_CODE_BLOCK

            messages.append({"role": "assistant",
                             "content": "" if message is None else message})
            messages.append({"role": "user",
                             "content": "Sandbox output:\n" + observation})
            print(f"\n{YELLOW}SANDBOX:\n{observation}{RESET}")

        return MAX_TURN_ERROR

    async def process_mbpp(self, task: MBPPTaskInput,
                           args: Any) -> SolutionOutput:
        system_prompt = build_system_prompt_mbpp(self.sandbox)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""This is an MBPP task.
Write the requested Python function using the exact function signature.
Before calling final_answer(), you MUST verify your solution by calling: run_tests(code)
Only call final_answer(code) after all tests pass.

Task: {task.task_definition}
Function Definition: {task.function_definition}
Test Cases from run_tests(): {task.test_list}"""},
        ]

        steps = []
        success = False
        message = ""
        sandbox_input = ""
        observation = ""
        total_requests = 0
        start = time.perf_counter()
        for i in range(MBPP_MAX_TURN):
            print(f"\nTURN: ({i+1}/{MBPP_MAX_TURN}):")

            print("connecting...")
            (response, request_time_ms,
             retries) = await self.create_completion(messages)
            total_requests += retries + 1

            input_tokens, output_tokens = token_counts(response)
            message = response.choices[0].message.content
            print(message)

            if is_safety_status_response(message or ""):
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was provider safety metadata, not an agent "
                        "response. Do not output safety labels; follow the required Thought and "
                        "single Python code-block format."
                    ),
                })
                continue

            try:
                matches = re.findall(r"```python\s*([\s\S]*?)```",
                                     message if message else "")
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
            elif len(matches) > 0:
                observation = MORE_THAN_ONE_CODE_BLOCK
            else:
                observation = NO_CODE_BLOCK

            messages.append({"role": "assistant",
                             "content": message if message else ""})
            messages.append({"role": "user",
                             "content": "Sandbox output:\n" + observation})
            print(f"\n{YELLOW}SANDBOX:\n{observation}{RESET}")

            steps.append(StepMetrics(
                step=i + 1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_time_ms=request_time_ms,
                api_url=args.provider_url,
                model_name=args.model_name,
                llm_output=message,
                sandbox_input=sandbox_input,
                sandbox_output=observation,
                retries=retries
            ))
            if (success):
                break

        error = None
        if success is False:
            error = MAX_TURN_ERROR

        return SolutionOutput(
            task_id=str(task.task_id),
            benchmark="mbpp",
            success=success,
            solution=result.final_answer if result.final_answer else "",
            iterations=len(steps),
            total_requests=total_requests,
            total_input_tokens=sum(step.input_tokens for step in steps),
            total_output_tokens=sum(step.output_tokens for step in steps),
            total_time_seconds=round(time.perf_counter() - start, 2),
            steps=steps,
            system_prompt=system_prompt,
            error=error
        )

    async def process_swebench(self, task: SWEBenchTaskInput,
                               args: Any) -> SolutionOutput:
        pass

    async def setup_docker(self, task: SWEBenchTaskInput, args: Any) -> tuple[Any, Any]:
        client = docker.from_env()

        print("downloading image...")
        image = client.images.pull(task.docker_image)

        transport = "stdio"

        print("creating...")
        container = client.containers.create(
            image=image,
            name="swebench_container",
            command="sleep infinity",
            ports={
                "8000/tcp": 8000
            } if transport == "streamable-http" else None,
        )

        print("starting...")
        container.start()

        copy_to_container(
            container,
            "mcp_tools_swebench.py",
            "/mcp_tools_swebench.py"
        )

        print("installing dependencies...")
        container.exec_run(
            "pip install dotenv 'mcp[cli]'"
        )

        if transport == "streamable-http":
            print("starting HTTP server...")

            container.exec_run(
                "python3 /mcp_tools_swebench.py "
                "--transport streamable-http "
                "--allowed-directory /testbed",
                detach=True
            )

            args.target = "http://localhost:8000/mcp"

            return (container, None)

        elif transport == "stdio":
            print("starting stdio server...")

            exec_id = client.api.exec_create(
                container.id,
                "python3 /mcp_tools_swebench.py "
                "--transport stdio "
                "--allowed-directory /testbed",
                stdin=True,
                stdout=True,
                stderr=True,
                tty=False,
            )

            socket = client.api.exec_start(
                exec_id,
                stream=True,
                socket=True
            )

            return (container, socket)




    async def chat_loop(self) -> None:
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if query.lower() == "quit":
                break

            try:
                response = await self.process_query(query)
                print(f"\n{response}")
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self) -> None:
        """Clean up resources"""
        await self.sandbox.close()
        await self.exit_stack.aclose()


async def real_main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", default="task.json")
    ap.add_argument("--output", default="solution.json")
    ap.add_argument("--model-name", default="openai/gpt-oss-120b")
    ap.add_argument("--provider-url", default="https://api.groq.com/openai/v1")
    ap.add_argument("--target", default="agent_mbpp/mcp_tools_mbpp.py")
    args = ap.parse_args()

    if args.task_file is not None:
        try:
            with open(args.task_file, "r") as f:
                data = json.load(f)
            task = MBPPTaskInput.model_validate(data)
        except Exception:
            task = None

        if not task:
            try:
                with open(args.task_file, "r") as f:
                    data = json.load(f)
                task = SWEBenchTaskInput.model_validate(data)
            except Exception:
                task = None

        if not task:
            print("Invalid task JSON")
            return

    client = Orchestrator(args.model_name, args.provider_url, args.target)

    try:
        if isinstance(task, MBPPTaskInput):
            await client.sandbox.start_mcp_client("mbpp", task.test_imports, task.test_list)
        elif isinstance(task, SWEBenchTaskInput):
            await client.setup_docker(task, args)
            await client.sandbox.start_mcp_client("swebench")

        api_key = os.getenv("OPENROUTER_API")
        if not api_key:
            print("Invalid or no API key")
            return

        if task is not None:
            if isinstance(task, MBPPTaskInput):
                result = await client.process_mbpp(task, args)
            elif isinstance(task, SWEBenchTaskInput):
                result = await client.process_swebench(task, args)
            print(f"{GREEN}FINAL ANSWER:\n{result.solution}{RESET}\n")
            solution = result.model_dump_json(indent=4)
            print(solution)
            with open(args.output, "w") as f:
                f.write(solution)
        else:
            await client.chat_loop()
    finally:
        await client.cleanup()


def main() -> None:
    asyncio.run(real_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
