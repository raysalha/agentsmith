import os
import argparse
import io
import traceback
from contextlib import redirect_stdout
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

IMPORTS: tuple[str, ...] = ()
TESTS: tuple[str, ...] = ()

mcp = FastMCP("agent_bob")


@mcp.tool()
def run_tests(code: str) -> str:
    """
    Execute generated code against a list of tests and Returns a human-readable report.
    """

    namespace = {}

    stdout = io.StringIO()

    try:
        with redirect_stdout(stdout):
            # Execute required imports
            for stmt in IMPORTS:
                exec(stmt, namespace)

            # Execute generated code
            exec(code, namespace)

            # Execute tests
            passed = 0
            failed = []

            for i, test in enumerate(TESTS, start=1):
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
        return (
            "Code failed to execute.\n\n"
            + traceback.format_exc()
        )

    report = []

    report.append(f"Passed {passed}/{len(TESTS)} tests.")

    output = stdout.getvalue()
    if output:
        report.append("\nCaptured stdout:")
        report.append(output.rstrip())

    if failed:
        report.append("\nFailed tests:\n")

        for failure in failed:
            report.append(f"Test #{failure['index']}:")
            report.append(failure["test"])
            report.append(failure["traceback"])

    else:
        report.append("\nAll tests passed.\nyou can now run final_answer()")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--allowed-directory", action="append", default=[])
    parser.add_argument("--imports", action="append", default=[])
    parser.add_argument("--tests", action="append", default=[])
    args = parser.parse_args()

    global IMPORTS
    IMPORTS = tuple(imp for imp in args.imports)

    if not args.tests:
        parser.error("at least one --tests is required")
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
