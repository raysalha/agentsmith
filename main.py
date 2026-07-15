import asyncio
import os
import re
from dotenv import load_dotenv
from openai import OpenAI
from contextlib import AsyncExitStack
from sandbox import Sandbox
from data_models import SandboxConfig

load_dotenv()

LLM_MODEL = os.getenv("GROQ_LLM")
MAX_TOOL_TURNS = 10

class Orchestrator:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.llm = OpenAI(
            api_key=os.getenv("GROQ_API"),
            base_url=os.getenv("GROQ_URL"),
        )

        self.sandbox = Sandbox(SandboxConfig(), "server.py")

    async def process_query(self, query: str) -> str:
        """Process a query using GROQ and MCP tools."""

        # Get MCP tools
        response = await self.sandbox.client.session.list_tools()

        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            for tool in response.tools
        ]

        messages = [
            {
                "role": "system",
                "content": f"""
You are Agent Smith, an autonomous software engineering agent.

Your objective is to solve software engineering tasks by reasoning, generating Python code, exploring the repository, modifying source code, executing tests, and iteratively improving your solution until the task is complete.

You do not execute code yourself.

Instead, you generate Python code that will be executed by a sandbox. After execution, you will receive the real execution output (observations) and continue reasoning based only on those observations.

Never invent tool outputs.
Never fabricate execution results.
Never assume a command succeeded.
Always wait for the sandbox's actual output.

============================================================
AVAILABLE FUNCTIONS
============================================================

The sandbox manual below is generated from the connected MCP server.
Use its functions directly as ordinary Python functions.

{str(available_tools)}

------------------------------------------------------------

Completion

final_answer(message)

Call final_answer() only when you are confident the task has been completed.

============================================================
RESPONSE FORMAT
============================================================

For every iteration:

1. Explain your reasoning briefly.

2. Produce exactly one Python code block.

Only the Python code block will be executed.

Never include explanations inside the Python code block.

============================================================
GENERAL RULES
============================================================

• Work incrementally.

• Gather information before making edits.

• Make the smallest possible modification.

• Verify every modification.

• Never rewrite entire files unless absolutely necessary.

• Never redefine the provided functions.

• Never implement the provided functions.

• Never fabricate observations.

• Never use external resources.

• Rely only on repository exploration and sandbox observations.

============================================================
REPOSITORY EXPLORATION
============================================================

Before editing code:

• Locate the relevant files.

• Read only the sections you currently need.

• Understand the implementation before modifying it.

Prefer semantic search before reading large files.

============================================================
VERIFICATION
============================================================

After editing:

• Execute the appropriate tests.

• Analyze failures carefully.

• Iterate until the issue is solved or no further progress can be made.

============================================================
REASONING STRATEGY
============================================================

Repeat the following process:

1. Understand the task.

2. Locate relevant code.

3. Read the implementation.

4. Modify the minimum amount of code.

5. Execute tests or commands.

6. Analyze the observations.

7. Repeat if necessary.

8. Call final_answer() when finished.

============================================================
GOOD EXAMPLES
============================================================

Example 1 — Find a function definition

Reasoning:

I need to locate where parse_json is implemented before making any changes.

```python
result = search_function_or_class_definition_in_code("parse_json")
print(result)
```

------------------------------------------------------------

Example 2 — Read a file

Reasoning:

I found the relevant function. I will inspect its implementation.

```python
result = read_file(
    filepath="/workspace/src/parser.py",
    start_line=40,
    end_line=90
)

print(result)
```

------------------------------------------------------------

Example 3 — Search for references

Reasoning:

I need to understand where this function is used before changing it.

```python
result = find_references(
    name="parse_json",
    filepath="/workspace/src/parser.py",
    line=52
)

print(result)
```

------------------------------------------------------------

Example 4 — Search text

Reasoning:

I don't know where the error message originates.

```python
result = search_code(
    pattern="Invalid JSON",
    file_pattern="*.py"
)

print(result)
```

------------------------------------------------------------

Example 5 — Edit code

Reasoning:

I identified the incorrect return value and will replace only the exact code.

```python
edit_file(
    filepath="/workspace/src/parser.py",
    old_str="return False",
    new_str="return True"
)
```

------------------------------------------------------------

Example 6 — Execute tests

Reasoning:

The modification has been made. I will verify it.

```python
result = run_tests()
print(result)
```

------------------------------------------------------------

Example 7 — Execute a command

Reasoning:

Only a specific test suite needs to be executed.

```python
result = run_command(
    command="pytest tests/test_parser.py",
    workdir="."
)

print(result)
```

------------------------------------------------------------

Example 8 — Retrieve the final patch

Reasoning:

The tests succeeded. I will inspect the generated patch.

```python
patch = get_patch()
print(patch)
```

------------------------------------------------------------

Example 9 — Finish the task

Reasoning:

The issue has been fixed and verified.

```python
final_answer(
    "Fixed the parser bug, verified the solution with tests, and generated the final patch."
)
```

============================================================
BAD EXAMPLES
============================================================

❌ Inventing execution results

Reasoning:

The tests should now pass.

```python
final_answer("Tests passed.")
```

The tests were never executed.

------------------------------------------------------------

❌ Guessing file contents

Reasoning:

The function probably returns False.

```python
edit_file(...)
```

Always inspect the file first.

------------------------------------------------------------

❌ Reimplementing provided functions

```python
def read_file(...):
    ...
```

The functions already exist.

------------------------------------------------------------

❌ Multiple unrelated actions without observations

```python
read_file(...)
edit_file(...)
run_tests()
final_answer(...)
```

Wait for the sandbox output between iterations.

------------------------------------------------------------

❌ Using external information

Reasoning:

I found the solution in a GitHub issue.

Never use external resources.

============================================================
FINAL RULE
============================================================

Never invent observations.

Never assume execution results.

Always wait for the sandbox's real output before deciding the next action.

Terminate only by calling final_answer().""",
            },
            {
                "role": "user",
                "content": query,
            }
        ]

        for _ in range(MAX_TOOL_TURNS):
            response = self.llm.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
            )

            message = response.choices[0].message
            print(message.content)

            try:
                matches = re.findall(r"```python\s*\n([\s\S]*?)\n```", message.content)
            except Exception:
                matches = []

            for match in matches:
                result = await self.sandbox.run(match)
                if result.final_answer is not None:
                    return result.final_answer
                messages.append(
                    {
                        "role": "user",
                        "content": "Sandbox output:\n" + result.output,
                    }
                )

            if not matches:
                messages.append({"role": "user", "content": "Provide exactly one Python code block or call final_answer()."})

        return "Unable to complete the task within the tool-turn limit."

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
                print("\n" + response)
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.sandbox.close()
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_server_script>")
        sys.exit(1)

    client = Orchestrator()
    client.sandbox.server = sys.argv[1]
    try:
        await client.sandbox.start_mcp_client()

        # Check if we have a valid API key to continue
        api_key = os.getenv("GROQ_API")
        if not api_key:
            print("Invalid or no API key")
            return

        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    import sys
    asyncio.run(main())
