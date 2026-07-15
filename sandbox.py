import asyncio
from dataclasses import dataclass
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

    async def start_mcp_client(self):
        self.client = MCPClient()
        await self.client.connect_to_server(self.server)

    def safe_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if any(name == allowed or (allowed.endswith(".*") and name.startswith(allowed[:-1]))
               for allowed in self.authorized_imports):
            return __import__(name, globals, locals, fromlist, level)

        raise ImportError(f"Import '{name}' is not allowed.")

    def final_answer(self, answer):
        raise FinalAnswer(str(answer))

    async def run(self, code: str) -> "SandboxResult":
        """Execute one model turn with dynamically discovered MCP tools."""

        namespace = {
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
                "__import__": self.safe_import,
            },
            "final_answer": self.final_answer,
        }

        try:
            exec(code, namespace)
        except FinalAnswer as e:
            return SandboxResult(output="", final_answer=e.answer)
        except asyncio.TimeoutError:
            raise RuntimeError("Sandbox execution timed out.")
        except (KeyboardInterrupt, SystemExit):
            raise
        except MemoryError:
            raise RuntimeError("Sandbox exceeded memory limit.")
        except Exception as e:
            raise RuntimeError(f"Sandbox execution failed: {e}")

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


def main():
    pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
