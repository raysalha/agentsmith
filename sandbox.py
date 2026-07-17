import asyncio
import builtins
import contextlib
from dataclasses import dataclass
import io
import multiprocessing
from client import MCPClient
from data_models import SandboxConfig


AUTHORIZED_BUILTINS = (
    "print", "len", "range", "str", "int", "float", "bool", "list", "dict",
)


class Sandbox:
    def __init__(self, conf: SandboxConfig, server: str):
        self.authorized_imports = conf.authorized_imports
        self.allowed_directories = conf.allowed_directories
        self.authorized_builtins = list(AUTHORIZED_BUILTINS)
        self.max_execution_time_seconds = conf.max_execution_time_seconds
        self.max_memory_mb = conf.max_memory_mb
        self.server = server
        self.client: MCPClient | None = None

    async def start_mcp_client(self):
        self.client = MCPClient()
        await self.client.connect_to_server(self.server)
        response = await self.client.session.list_tools()
        self.tool_parameters = {
            tool.name: tuple((tool.inputSchema or {}).get("properties", ()))
            for tool in response.tools
        }

    async def run(self, code: str) -> "SandboxResult":
        """Execute one model turn in a separate process.

        MCP sessions are not safe to share with a child process, so tool calls are
        sent back to this process over a pipe and executed against the live session.
        """

        parent_conn, child_conn = multiprocessing.Pipe()
        process = multiprocessing.get_context("spawn").Process(
            target=_execute_in_child,
            args=(
                child_conn,
                code,
                self.authorized_imports,
                self.authorized_builtins,
                self.tool_parameters,
                self.max_memory_mb,
            ),
        )
        process.start()
        child_conn.close()

        loop = asyncio.get_running_loop()
        result: asyncio.Future[dict] = loop.create_future()
        tool_tasks: set[asyncio.Task] = set()

        async def handle_tool_call(tool_name: str, kwargs: dict) -> None:
            try:
                call_result = await self.client.session.call_tool(tool_name, kwargs)
                output = "\n".join(
                    block.text for block in call_result.content if hasattr(block, "text")
                )
                parent_conn.send(("tool_result", output))
            except Exception as exc:
                parent_conn.send(("tool_error", str(exc)))

        def receive_child_message() -> None:
            try:
                while parent_conn.poll():
                    message_type, *payload = parent_conn.recv()
                    if message_type == "tool_call":
                        task = asyncio.create_task(handle_tool_call(*payload))
                        tool_tasks.add(task)
                        task.add_done_callback(tool_tasks.discard)
                    elif message_type == "result" and not result.done():
                        result.set_result(payload[0])
            except EOFError:
                if not result.done():
                    result.set_result({"error": "Sandbox process exited unexpectedly"})

        loop.add_reader(parent_conn.fileno(), receive_child_message)
        try:
            worker_result = await asyncio.wait_for(result, timeout=self.max_execution_time_seconds)
            return SandboxResult(**worker_result)
        except asyncio.TimeoutError:
            return SandboxResult(output="", error="Execution timed out")
        finally:
            loop.remove_reader(parent_conn.fileno())
            for task in tool_tasks:
                task.cancel()
            if process.is_alive():
                process.terminate()
            process.join()
            parent_conn.close()

    async def close(self):
        if self.client is not None:
            await self.client.exit_stack.aclose()


class FinalAnswer(Exception):
    def __init__(self, answer: str):
        self.answer = answer


@dataclass
class SandboxResult:
    output: str
    final_answer: str | None = None
    error: str | None = None


def _execute_in_child(
    conn,
    code: str,
    authorized_imports: list[str],
    authorized_builtins: list[str],
    tool_parameters: dict[str, tuple[str, ...]],
    max_memory_mb: int,
) -> None:
    """Child-process entry point for untrusted model code."""

    import resource
    try:
        max_bytes = max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
    except (ValueError, resource.error):
        pass

    stdout_buf = io.StringIO()

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if any(
            name == allowed or (allowed.endswith(".*") and name.startswith(allowed[:-1]))
            for allowed in authorized_imports
        ):
            return __import__(name, globals, locals, fromlist, level)
        raise ImportError(f"Import '{name}' is not allowed.")

    def make_wrapper(tool_name, parameter_names):
        def wrapper(*args, **kwargs):
            if len(args) > len(parameter_names):
                raise TypeError(
                    f"{tool_name}() takes at most {len(parameter_names)} positional arguments "
                    f"but {len(args)} were given"
                )
            for parameter_name, value in zip(parameter_names, args):
                if parameter_name in kwargs:
                    raise TypeError(f"{tool_name}() got multiple values for '{parameter_name}'")
                kwargs[parameter_name] = value
            conn.send(("tool_call", tool_name, kwargs))
            message_type, payload = conn.recv()
            if message_type == "tool_result":
                return payload
            raise RuntimeError(payload)
        return wrapper

    def final_answer(answer):
        raise FinalAnswer(str(answer))

    namespace = {
        "__builtins__": {name: getattr(builtins, name) for name in authorized_builtins}
        | {"__import__": safe_import},
        "final_answer": final_answer,
    }
    namespace.update({
        name: make_wrapper(name, parameter_names)
        for name, parameter_names in tool_parameters.items()
    })

    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(code, namespace)
        conn.send(("result", {"output": stdout_buf.getvalue()}))
    except FinalAnswer as exc:
        conn.send(("result", {"output": stdout_buf.getvalue(), "final_answer": exc.answer}))
    except (KeyboardInterrupt, SystemExit):
        raise
    except MemoryError:
        conn.send(("result", {"output": stdout_buf.getvalue(), "error": "Sandbox exceeded memory limit."}))
    except Exception as exc:
        conn.send(("result", {"output": stdout_buf.getvalue(), "error": f"Sandbox execution failed: {exc}"}))
    finally:
        conn.close()


def main():
    pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
