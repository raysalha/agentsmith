import re
import os
import fnmatch
import subprocess
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = os.getenv("AGENT_REPO_ROOT")
EVAL_SCRIPT_PATH = os.getenv("AGENT_EVAL_SCRIPT")

mcp = FastMCP("agent_bob")


def _resolve_and_check(path: str) -> tuple[str, str | None]:
    """Resolve `path` to an absolute path and make sure it stays within
    REPO_ROOT. Returns (abs_path, error_message). error_message is None if
    the path is fine.
    """
    if not REPO_ROOT:
        return "", "Error: AGENT_REPO_ROOT is not configured"
    if not path:
        return "", "Error: a path is required"

    abs_root = os.path.realpath(REPO_ROOT)
    abs_path = os.path.realpath(os.path.join(abs_root, path) if not os.path.isabs(path) else path)

    if os.path.commonpath([abs_root, abs_path]) != abs_root:
        return abs_path, f"Error: path '{path}' is outside the allowed directory ({abs_root})"

    return abs_path, None


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read a file's content with line numbers, cat -n style."""
    abs_path, err = _resolve_and_check(filepath)
    if err:
        return err

    if start_line < 1 or end_line < start_line:
        return f"Error: invalid line range ({start_line}, {end_line})"

    if not os.path.isfile(abs_path):
        return f"Error: file not found: {filepath}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, PermissionError, OSError) as e:
        return f"Error: could not read '{filepath}': {e}"

    if start_line > len(lines):
        return f"Error: start_line {start_line} exceeds file length ({len(lines)} lines)"

    selected = lines[start_line - 1:end_line]
    if not selected:
        return f"Error: no lines in range {start_line}-{end_line}"

    return "\n".join(
        f"{i}: {line.rstrip()}"
        for i, line in enumerate(selected, start=start_line)
    )


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string."""
    abs_path, err = _resolve_and_check(filepath)
    if err:
        return err

    if not os.path.isfile(abs_path):
        return f"Error: file not found: {filepath}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError, OSError) as e:
        return f"Error: could not read '{filepath}': {e}"

    if old_str not in content:
        return f"Error: old_str not found in '{filepath}'. No changes made."

    count = content.count(old_str)
    if count > 1:
        return (
            f"Error: old_str is not unique in '{filepath}' ({count} occurrences). "
            f"Provide more surrounding context to make it unique. No changes made."
        )

    new_content = content.replace(old_str, new_str)

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except OSError as e:
        return f"Error: could not write '{filepath}': {e}"

    return f"OK: file '{filepath}' updated successfully."


@mcp.tool()
def list_files(directory: str, pattern: str = "*") -> list[str]:
    """List files in a directory matching a given pattern."""
    abs_path, err = _resolve_and_check(directory)
    if err:
        return [err]

    if not os.path.isdir(abs_path):
        return [f"Error: directory not found: {directory}"]

    res = []
    try:
        for entry in sorted(os.listdir(abs_path)):
            if fnmatch.fnmatch(entry, pattern):
                res.append(os.path.join(abs_path, entry))
    except OSError as e:
        return [f"Error: could not list '{directory}': {e}"]

    return res


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*.py") -> str:
    """Grep-like search across the repo. Returns 'path:line content' rows."""
    if not REPO_ROOT:
        return "Error: AGENT_REPO_ROOT is not configured"
    res = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip common noise directories so results stay useful/fast.
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for file in files:
            if fnmatch.fnmatch(file, file_pattern):
                filepath = os.path.abspath(os.path.join(root, file))
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, start=1):
                            if pattern in line:
                                res.append(f"{filepath}:{i} {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError, OSError):
                    continue

    if not res:
        return f"No matches found for pattern '{pattern}' in files matching '{file_pattern}'."

    return "\n".join(res)


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Find the definition of a function or class by name."""
    if not REPO_ROOT:
        return "Error: AGENT_REPO_ROOT is not configured"
    res = []
    pattern = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b")

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for file in files:
            if fnmatch.fnmatch(file, "*.py"):
                filepath = os.path.abspath(os.path.join(root, file))
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, start=1):
                            if pattern.search(line):
                                res.append(f"{filepath}:{i} {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError, OSError):
                    continue

    if not res:
        return f"No definition found for '{name}'."

    return "\n".join(res)


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> str:
    """Find all usages of a symbol, excluding its own definition site."""
    if not REPO_ROOT:
        return "Error: AGENT_REPO_ROOT is not configured"
    abs_def_path, err = _resolve_and_check(filepath)
    if err:
        return err

    res = []
    pattern = re.compile(rf"\b{re.escape(name)}\b")

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for file in files:
            if not file.endswith(".py"):
                continue
            abs_path = os.path.abspath(os.path.join(root, file))
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    for i, l in enumerate(f, start=1):
                        if pattern.search(l):
                            if abs_path == abs_def_path and i == line:
                                continue
                            res.append(f"{abs_path}:{i} {l.rstrip()}")
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

    if not res:
        return f"No references found for '{name}'."

    return "\n".join(res)


@mcp.tool()
def run_tests() -> str:
    """Execute the evaluation script and report the outcome."""
    if not REPO_ROOT:
        return "Error: AGENT_REPO_ROOT is not configured"
    if not EVAL_SCRIPT_PATH or not os.path.isfile(EVAL_SCRIPT_PATH):
        return f"Error: eval script not found at {EVAL_SCRIPT_PATH}"

    try:
        result = subprocess.run(
            ["bash", EVAL_SCRIPT_PATH],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return "Error: test execution timed out after 600s"
    except OSError as e:
        return f"Error: could not run eval script: {e}"

    return (
        f"exit_code: {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


@mcp.tool()
def get_patch() -> str:
    """Return the unified git diff of all changes made to the repository."""
    if not REPO_ROOT:
        return "Error: AGENT_REPO_ROOT is not configured"
    try:
        result = subprocess.run(
            ["git", "-c", "core.fileMode=false", "diff"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "Error: git diff timed out"
    except OSError as e:
        return f"Error: could not run git diff: {e}"

    if result.returncode != 0:
        return f"Error: git diff failed (exit {result.returncode}): {result.stderr}"

    if not result.stdout.strip():
        return "Error: no changes detected (empty diff)"

    return result.stdout


@mcp.tool()
def run_command(command: str, workdir: str = ".") -> str:
    abs_workdir, err = _resolve_and_check(workdir)
    if err:
        return err
    if not os.path.isdir(abs_workdir):
        return f"Error: working directory not found: {workdir}"

    try:
        result = subprocess.run(
            command,
            shell=True,          # <-- lets >, |, &&, heredocs etc. work
            cwd=abs_workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after 120s: {command}"
    except OSError as e:
        return f"Error: could not run command: {e}"

    return f"exit_code: {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
