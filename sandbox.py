import asyncio
import contextlib
from dataclasses import dataclass
import io
from client import MCPClient
from data_models import SandboxConfig


class Sandbox:
    def __init__(self, conf: SandboxConfig, server: str):
        self.allowed_directories = conf.allowed_directories
        self.authorized_imports = conf.authorized_imports
        self.max_execution_time_seconds = conf.max_execution_time_seconds
        self.max_memory_mb = conf.max_memory_mb
        self.server = server
        self.client: MCPClient | None = None
        self.namespace: dict | None = None

    async def start_mcp_client(self):
        self.client = MCPClient()
        await self.client.connect_to_server(self.server)
        await self._build_namespace()

    def safe_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if any(name == allowed or (allowed.endswith(".*") and name.startswith(allowed[:-1]))
               for allowed in self.authorized_imports):
            return __import__(name, globals, locals, fromlist, level)

        raise ImportError(f"Import '{name}' is not allowed.")

    def final_answer(self, answer):
        raise FinalAnswer(str(answer))

    async def _build_namespace(self):
        response = await self.client.session.list_tools()
        loop = asyncio.get_running_loop()

        def make_wrapper(tool_name):
            def wrapper(**kwargs):
                future = asyncio.run_coroutine_threadsafe(
                    self.client.session.call_tool(tool_name, kwargs), loop
                )
                result = future.result(timeout=self.max_execution_time_seconds)
                return "\n".join(b.text for b in result.content if hasattr(b, "text"))
            return wrapper

        self.namespace = {
            "__builtins__": {
                "print": print,
                "len": len,
                "range": range,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "__import__": self.safe_import,},  # your existing safe builtins dict
            "final_answer": self.final_answer,
        }
        for tool in response.tools:
            self.namespace[tool.name] = make_wrapper(tool.name)

    async def run(self, code: str) -> "SandboxResult":
        """Execute one model turn with dynamically discovered MCP tools."""
        if self.namespace is None:
            raise RuntimeError("Namespace not initialized — call _build_namespace() first")


        stdout_buf = io.StringIO()
        def _exec():
            with contextlib.redirect_stdout(stdout_buf):
                exec(code, self.namespace)
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(loop.run_in_executor(None, _exec), timeout=self.max_execution_time_seconds)
            return SandboxResult(output=stdout_buf.getvalue())
        except FinalAnswer as e:
            return SandboxResult(output=stdout_buf.getvalue(), final_answer=e.answer)
        except asyncio.TimeoutError:
            return SandboxResult(output=stdout_buf.getvalue(), error="Execution timed out")
        except (KeyboardInterrupt, SystemExit):
            raise
        except MemoryError:
            raise RuntimeError("Sandbox exceeded memory limit.")
        except Exception as e:
            return SandboxResult(output=stdout_buf.getvalue(), error=f"Sandbox execution failed: {e}")

    async def close(self):
        if self.client is not None:
            await self.client.exit_stack.aclose()


class FinalAnswer(BaseException):
    def __init__(self, answer: str):
        self.answer = answer


@dataclass
class SandboxResult:
    output: str
    final_answer: str | None = None
    error: str | None = None


def main():
    pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
