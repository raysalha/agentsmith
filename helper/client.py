import os
import shlex
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class MCPClient:
    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_server(
        self, target: str, eval_script: Optional[str],
        allowed_directories: list[str] | None = None,
        imports: list[str] | None = None,
        tests: list[str] | None = None,
    ) -> None:
        if target.startswith(("http://", "https://")):
            read, write, *_ = await self.exit_stack.enter_async_context(
                streamable_http_client(target)
            )
        else:
            command = target.strip()
            if not command:
                raise ValueError("MCP server target cannot be empty")

            parts = shlex.split(command, posix=True)
            if not parts:
                raise ValueError("MCP server target could not be parsed")

            executable = parts[0]
            args = parts[1:]
            cwd = None
            script_path = None

            if executable in {"python", "python3"}:
                executable = sys.executable
                if args and os.path.splitext(args[0])[1] == ".py":
                    script_path = args[0]
                    args = [script_path, *args[1:]]
            elif os.path.splitext(executable)[1] == ".py":
                script_path = executable
                executable = sys.executable
                args = [script_path, *args]

            if script_path is not None:
                script = Path(script_path).expanduser()
                if not script.is_absolute():
                    script = (Path.cwd() / script).resolve()
                cwd = str(script.parent)

            should_pass_tool_args = (
                script_path is not None
                and Path(script_path).name in {"mcp_tools_mbpp.py", "mcp_tools_swebench.py"}
            )
            if should_pass_tool_args:
                for directory in allowed_directories or []:
                    args.extend(["--allowed-directory",
                                 str(Path(directory).resolve())])
                for imp in imports or []:
                    args.extend(["--imports", str(imp)])
                for test in tests or []:
                    args.extend(["--tests", str(test)])
            if eval_script and should_pass_tool_args:
                args.extend(["--eval-script", eval_script])

            server_params = StdioServerParameters(
                command=executable,
                args=args,
                cwd=cwd,
            )

            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        self.tools = response.tools
        print("\nConnected to server with tools:",
              [tool.name for tool in self.tools])
