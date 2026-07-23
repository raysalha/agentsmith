from contextlib import AsyncExitStack
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class MCPClient:
    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_server(
        self, target: str,
        server_type: str,
        allowed_directories: list[str] | None = None,
        imports: list[str] | None = None,
        tests: list[str] | None = None,
    ) -> None:
        if target.startswith(("http://", "https://")):
            read, write, *_ = await self.exit_stack.enter_async_context(
                streamable_http_client(target)
            )
        else:
            path = Path(target).resolve()
            args = ["--directory", str(path.parent), "run", path.name]
            for directory in allowed_directories or []:
                args.extend(["--allowed-directory",
                             str(Path(directory).resolve())])
            for imp in imports or []:
                args.extend(["--imports", str(imp)])
            for test in tests or []:
                args.extend(["--tests", str(test)])
        if server_type == "swebench":
            pass
        else:
            server_params = StdioServerParameters(
                command="uv",
                args=args,
            )

            read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))

        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        self.tools = response.tools
        print("\nConnected to server with tools:",
              [tool.name for tool in self.tools])
