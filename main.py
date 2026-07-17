import argparse
import asyncio
import json
import os
import sys
import re
from misc import *
from dotenv import load_dotenv
from openai import OpenAI
from contextlib import AsyncExitStack
from sandbox import Sandbox
from data_models import MBPPTaskInput, SWEBenchTaskInput, SandboxConfig
from system_prompt import build_system_prompt

load_dotenv()

MAX_TOOL_TURNS = 10

class Orchestrator:
    def __init__(self, model: str, url: str):
        self.exit_stack = AsyncExitStack()
        self.model = model
        self.llm = OpenAI(
            api_key=os.getenv("OPENROUTER_API"),
            base_url=url,
        )

        self.sandbox = Sandbox(SandboxConfig(), "server.py")

    async def process_query(self, query: str) -> str:
        """Process a query using OPENROUTER and MCP tools."""

        # Get MCP tools
        response = await self.sandbox.client.session.list_tools()
        system_prompt = build_system_prompt(response.tools, self.sandbox.authorized_imports, self.sandbox.authorized_builtins)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        for i in range(MAX_TOOL_TURNS):
            print(f"TURN: ({i+1}/{MAX_TOOL_TURNS}):")
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            message = response.choices[0].message
            print(message.content)

            try:
                matches = re.findall(r"```python\s*\n([\s\S]*?)\n```", message.content)
            except Exception:
                matches = []

            if len(matches) == 1:
                result = await self.sandbox.run(matches[0])
                if result.final_answer is not None:
                    return f"{GREEN}FINAL ANSWER: {result.final_answer}{RESET}"
                observation = result.output
                if result.error:
                    observation += f"\n{RED}ERROR: {result.error}{RESET}"

                messages.append({"role": "assistant", "content": message.content})

                messages.append({"role": "user", "content": "Sandbox output:\n" + observation})

                print(f"{YELLOW}SANDBOX:\n{observation}{RESET}")
            elif len(matches) > 0:
                print(YELLOW + MORE_THAN_ONE_CODE_BLOCK + RESET)
                messages.append({
                    "role": "user",
                    "content": MORE_THAN_ONE_CODE_BLOCK
                })
            else:
                print(YELLOW + NO_CODE_BLOCK + RESET)
                messages.append({
                    "role": "user",
                    "content": NO_CODE_BLOCK
                })

        return RED + "FINAL ANSWER: Unable to complete the task within the tool-turn limit." + RESET

    async def chat_loop(self):
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
                print(f"\n", response)
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.sandbox.close()
        await self.exit_stack.aclose()


async def main():
    # if len(sys.argv) < 2:
    #     print("Usage: python main.py <path_to_server_script>")
    #     sys.exit(1)

    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", default="task.json")
    ap.add_argument("--output", default="solution.json")
    ap.add_argument("--model-name", default="openrouter/free")
    ap.add_argument("--provider-url", default="https://openrouter.ai/api/v1")
    args = ap.parse_args()

    with open(args.task_file, "r") as f:
        data = json.load(f)

    task = MBPPTaskInput.model_validate(data)

    client = Orchestrator(args.model_name, args.provider_url)

    try:
        await client.sandbox.start_mcp_client()

        api_key = os.getenv("OPENROUTER_API")
        if not api_key:
            print("Invalid or no API key")
            return

        if len(sys.argv) == 1:
            await client.chat_loop()
        else:
            result = await client.process_query(task.task_definition)
            print(result)
    finally:
        await client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
