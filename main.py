import argparse
import asyncio
import json
import os
import re
from typing import Any
from misc import RED, GREEN, YELLOW, RESET, NO_CODE_BLOCK, MORE_THAN_ONE_CODE_BLOCK
from dotenv import load_dotenv
from openai import OpenAI
from contextlib import AsyncExitStack
from sandbox import Sandbox
from data_models import MBPPTaskInput, SWEBenchTaskInput, SandboxConfig, SolutionOutput, StepMetrics
from system_prompt import build_system_prompt, build_system_prompt_mbpp

load_dotenv()

MAX_TOOL_TURNS = 10


class Orchestrator:
    def __init__(self, model: str, url: str, target: str):
        self.exit_stack = AsyncExitStack()
        self.model = model
        self.llm = OpenAI(
            api_key=os.getenv("OPENROUTER_API2"),
            base_url=url,
        )

        self.sandbox = Sandbox(SandboxConfig(), target)

    async def process_query(self, query: str) -> str:
        """Process a query using OPENROUTER and MCP tools."""

        messages = [
            {"role": "system", "content": build_system_prompt(self.sandbox)},
            {"role": "user", "content": query},
        ]

        for i in range(MAX_TOOL_TURNS):
            print(f"\nTURN: ({i+1}/{MAX_TOOL_TURNS}):")

            response = self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            message = response.choices[0].message.content
            print(message)

            try:
                matches = re.findall(r"```python\s*([\s\S]*?)```", "" if message is None else message)
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

            messages.append({"role": "assistant", "content": "" if message is None else message})
            messages.append({"role": "user", "content": "Sandbox output:\n" + observation})
            print(f"\n{YELLOW}SANDBOX:\n{observation}{RESET}")

        return RED + "FINAL ANSWER: Unable to complete the task within the tool-turn limit." + RESET

    async def process_mbpp(self, task: MBPPTaskInput, args: Any) -> SolutionOutput:
        system_prompt = build_system_prompt_mbpp(self.sandbox)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""This is an MBPP task.
Write the requested Python function using the exact function signature.
Before calling final_answer(), you MUST verify your solution by calling: run_tests(code)
Only call final_answer(code) after all tests pass.

Task: {task.task_definition}
Function Definition: {task.function_definition}"""},
        ]

        steps = []
        success = False
        for i in range(MAX_TOOL_TURNS):
            if (success):
                break
            print(f"\nTURN: ({i+1}/{MAX_TOOL_TURNS}):")

            response = self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            message = response.choices[0].message.content
            print(message)

            try:
                matches = re.findall(r"```python\s*([\s\S]*?)```", "" if message is None else message)
            except Exception:
                matches = []

            if len(matches) == 1:
                sandbox_input = matches[0]
                result = await self.sandbox.run(sandbox_input)
                if result.final_answer is not None:
                    success = True
                    final_answer = f"{GREEN}FINAL ANSWER: {result.final_answer}{RESET}"
                observation = result.output
                if result.error:
                    observation += f"{RED}ERROR: {result.error}{RESET}"
            elif len(matches) > 0:
                observation = MORE_THAN_ONE_CODE_BLOCK
            else:
                observation = NO_CODE_BLOCK

            messages.append({"role": "assistant", "content": "" if message is None else message})
            messages.append({"role": "user", "content": "Sandbox output:\n" + observation})
            print(f"\n{YELLOW}SANDBOX:\n{observation}{RESET}")

            step = StepMetrics(
                step=i + 1,
                input_tokens=0,
                output_tokens=0,
                request_time_ms=0.0,
                api_url=args.provider_url,
                model_name=args.model_name,
                llm_output="" if message is None else message,
                sandbox_input="" if sandbox_input is None else sandbox_input,
                sandbox_output="" if observation is None else observation,
                retries=0
            )
            steps.append(step)

        error = None
        if success is False:
            error = RED + "Unable to complete the task within the tool-turn limit." + RESET

        return SolutionOutput(
            task_id=str(task.task_id),
            benchmark="mbpp",
            success=success,
            solution=final_answer,
            iterations=len(steps),
            total_requests=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_time_seconds=0,
            steps=steps,
            system_prompt=system_prompt,
            error=error
        )

    async def process_swebench(self, task: SWEBenchTaskInput, args: Any) -> SolutionOutput:
        pass

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
    ap.add_argument("--model-name", default="openrouter/free")
    ap.add_argument("--provider-url", default="https://openrouter.ai/api/v1")
    ap.add_argument("--target", default=None)
    args = ap.parse_args()

    if args.task_file is not None:
        try:
            with open(args.task_file, "r") as f:
                data = json.load(f)
            task = MBPPTaskInput.model_validate(data)
        except Exception:
            task = None

        if task is None:
            try:
                with open(args.task_file, "r") as f:
                    data = json.load(f)
                task = SWEBenchTaskInput.model_validate(data)
            except Exception:
                task = None

    client = Orchestrator(args.model_name, args.provider_url, args.target)

    try:
        await client.sandbox.start_mcp_client(task.test_imports, task.test_list)

        api_key = os.getenv("OPENROUTER_API")
        if not api_key:
            print("Invalid or no API key")
            return

        if task is not None:
            if isinstance(task, MBPPTaskInput):
                result = await client.process_mbpp(task, args)
            elif isinstance(task, SWEBenchTaskInput):
                result = await client.process_swebench(task, args)
            print(result.solution)
            print("\n\n")
            print(result.steps)
            print("\n\n")
            print(result)
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
    except Exception as e:
        print(e)
