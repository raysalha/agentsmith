import argparse
import io
import json
import traceback
from contextlib import redirect_stdout
from typing import Any
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

IMPORTS: tuple[str, ...] = ()
TESTS: tuple[str, ...] = ()

mcp = FastMCP("agent_bob")


@mcp.tool()
def run_tests(code: str, test_list: list[str] | None = None) -> str:
    """Execute generated code against a list of tests and return JSON."""

    selected_tests = tuple(test_list or TESTS)
    namespace: dict[Any, Any] = {}
    stdout = io.StringIO()
    passed = 0
    failed = []

    try:
        with redirect_stdout(stdout):
            # Execute required imports
            for stmt in IMPORTS:
                exec(stmt, namespace)

            # Execute generated code
            exec(code, namespace)

            # Execute tests
            for i, test in enumerate(selected_tests, start=1):
                try:
                    exec(test, namespace)
                    passed += 1
                except Exception:
                    failed.append(
                        {
                            "index": i,
                            "test": test,
                            "traceback": traceback.format_exc(),
                        }
                    )

    except Exception:
        return json.dumps(
            {
                "success": False,
                "passed": 0,
                "total": len(selected_tests) if selected_tests else 0,
                "output": traceback.format_exc(),
            }
        )

    report_lines = []
    report_lines.append(f"Passed {passed}/{len(selected_tests)} tests.")

    output = stdout.getvalue()
    if output:
        report_lines.append("\nCaptured stdout:")
        report_lines.append(output.rstrip())

    if failed:
        report_lines.append("\nFailed tests:\n")
        for failure in failed:
            report_lines.append(f"Test #{failure['index']}:")
            report_lines.append(str(failure["test"]))
            report_lines.append(str(failure["traceback"]))
    else:
        e = "\nAll tests passed.\nyou can now run final_answer()"
        report_lines.append(e)

    payload = {
        "success": not failed,
        "passed": passed,
        "total": len(selected_tests),
        "output": "\n".join(report_lines),
    }
    return json.dumps(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"],
                        default="stdio")
    parser.add_argument("--allowed-directory", action="append", default=[])
    parser.add_argument("--imports", action="append", default=[])
    parser.add_argument("--tests", action="append", default=[])
    args = parser.parse_args()

    global IMPORTS
    IMPORTS = tuple(imp for imp in args.imports)

    global TESTS
    TESTS = tuple(test for test in args.tests)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
