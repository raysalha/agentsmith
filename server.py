import re
import os
import fnmatch
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("agent_bob")


@mcp.tool()
async def read_file(filepath: str, start_line: int, end_line: int) -> str:
    if start_line < 1 or end_line < start_line:
        raise ValueError("Invalid line range")

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    return "\n".join(
        f"{i}: {line.rstrip()}"
        for i, line in enumerate(lines[start_line - 1:end_line], start=start_line)
    )


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> int:
    try:
        with open(filepath, 'r') as file:
            content = file.read()

            new_content = content.replace(old_str, new_str)

            with open(filepath, 'w') as file:
                file.write(new_content)
    except Exception as e:
        return e
    return "OK"


@mcp.tool()
def list_files(directory: str, pattern: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    res = []
    for file in os.listdir(directory):
        # fnmatch correctly interprets wildcards like '*' and '?'
        if fnmatch.fnmatch(file, pattern):
            res.append(os.path.join(directory, file))
    return res


@mcp.tool()
def search_code(pattern: str, file_pattern: str) -> str:
    res = []

    for root, dirs, files in os.walk("."):
        for file in files:
            if fnmatch.fnmatch(file, file_pattern):
                filepath = os.path.abspath(os.path.join(root, file))
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, start=1):
                            if pattern in line:
                                res.append(f"{filepath}:{i} {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    continue

    return "\n".join(res)


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> None:
    res = []

    pattern = re.compile(
        rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b"
    )
    for root, dirs, files in os.walk("."):
        for file in files:
            if fnmatch.fnmatch(file, "*.py"):
                filepath = os.path.abspath(os.path.join(root, file))
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, start=1):
                            if pattern.search(line):
                                res.append(f"{filepath}:{i} {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    continue

    return "\n".join(res)


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> None:
    res = []
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    for root, dirs, files in os.walk("."):
        for file in files:
            if not file.endswith(".py"):
                continue
            abs_path = os.path.abspath(os.path.join(root, file))
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    for i, l in enumerate(f, start=1):

                        if pattern.search(l):
                            if (abs_path == filepath and i == line):
                                continue
                            res.append(f"{abs_path}:{i} {l.rstrip()}")
            except (UnicodeDecodeError, PermissionError):
                continue
    return "\n".join(res)


@mcp.tool()
def run_tests() -> None:
    pass


@mcp.tool()
def get_patch() -> None:
    pass


@mcp.tool()
def run_command(command: str, workdir: str) -> None:
    d = "cd " + workdir
    os.system(d)
    os.system(command)


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as e:
        print(e)
