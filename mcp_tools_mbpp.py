import os
import argparse
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

EVAL_SCRIPT_PATH = os.getenv("AGENT_EVAL_SCRIPT")
ALLOWED_DIRECTORIES: tuple[str, ...] = ()

mcp = FastMCP("agent_bob")


@mcp.tool()
def run_tests() -> str:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--allowed-directory", action="append", default=[])
    args = parser.parse_args()

    if not args.allowed_directory:
        parser.error("at least one --allowed-directory is required")
    global ALLOWED_DIRECTORIES
    ALLOWED_DIRECTORIES = tuple(os.path.realpath(path) for path in args.allowed_directory)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
