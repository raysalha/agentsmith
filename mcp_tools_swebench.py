import re
import os
import shlex
import argparse
import fnmatch
import subprocess
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

EVAL_SCRIPT_PATH: str = ""
ALLOWED_DIRECTORIES: tuple[str, ...] = ()

mcp = FastMCP("agent_bob")


def _bounded_output(text: str, limit: int = 16000) -> str:
    if len(text) <= limit:
        return text
    return (text[:limit // 2] +
            "\n...[output truncated]...\n" +
            text[-limit // 2:])


def _is_allowed(path: str) -> bool:
    return any(
        os.path.commonpath([directory, path]) == directory
        for directory in ALLOWED_DIRECTORIES
    )


def _resolve_and_check(path: str) -> tuple[str, str | None]:
    """Resolve a path within the allowlist,
       rejecting ambiguous relative paths."""
    if not ALLOWED_DIRECTORIES:
        return "", "Error: no allowed directories are configured"
    if not path:
        return "", "Error: a path is required"

    if os.path.isabs(path):
        abs_path = os.path.realpath(path)
        if _is_allowed(abs_path):
            return abs_path, None
        return (abs_path,
                f"Error: path '{path}' is outside the allowed directories")

    candidates = [os.path.realpath(os.path.join(directory, path))
                  for directory in ALLOWED_DIRECTORIES]
    candidates = [candidate for candidate in candidates
                  if _is_allowed(candidate)]
    if not candidates:
        return "", f"Error: path '{path}' is outside the allowed directories"

    matches = [candidate for candidate in candidates
               if os.path.exists(candidate)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        f = f"Error: relative path '{path}' is ambiguous; use an absolute path"
        return "", f

    return candidates[0], None


def _repository_root() -> str | None:
    """The first directory is the repository used for repo-wide operations."""
    return ALLOWED_DIRECTORIES[0] if ALLOWED_DIRECTORIES else None


def _is_safe_command(command: str) -> tuple[bool, str | None]:
    """Reject shell syntax or paths that could escape the allowlisted workspace."""
    if not command or not command.strip():
        return False, "Error: a command is required"

    blocked_tokens = (";", "&&", "||", "|", ">", "<", "$(", "`")
    if any(token in command for token in blocked_tokens):
        return False, (
            "Error: command contains blocked shell syntax; only simple "
            "single-command invocations are allowed"
        )

    try:
        parts = shlex.split(command, posix=True)
    except ValueError as exc:
        return False, f"Error: could not parse command: {exc}"

    for part in parts:
        if part in {".", ".."}:
            return False, "Error: path traversal is not allowed"

        if os.path.isabs(part):
            abs_part = os.path.realpath(part)
            if not _is_allowed(abs_part):
                return False, (
                    f"Error: command path '{part}' is outside the allowed directories"
                )
            continue

        if any(segment == ".." for segment in part.split(os.sep)):
            return False, "Error: path traversal is not allowed"

    return True, None


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """
    Read a contiguous range of lines from a text file.

    Use this tool to inspect the implementation of a function or class
    after locating it. The returned text is line-numbered to make it
    easier to reference locations in later edits.

    Arguments:
        filepath:
            Path to the file. May be absolute or relative to the repository.
        start_line:
            First line to read (1-indexed, inclusive).
        end_line:
            Last line to read (inclusive).

    Returns:
        A string containing the requested lines prefixed with line numbers.

    Typical workflow:
        search_function_or_class_definition_in_code(...)
        -> read_file(...)
        -> edit_file(...)

    Do not use this tool to search the repository. Use search_code() or
    search_function_or_class_definition_in_code() first.
    """
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
        return (
            f"Error: start_line {start_line} exceeds "
            f"file length ({len(lines)} lines)"
        )

    selected = lines[start_line - 1:end_line]
    if not selected:
        return f"Error: no lines in range {start_line}-{end_line}"

    return "\n".join(
        f"{i}: {line.rstrip()}"
        for i, line in enumerate(selected, start=start_line)
    )


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """
    Replace one exact block of text inside a file.

    The replacement is performed only if old_str matches exactly one
    location in the file.

    Arguments:
        filepath:
            File to modify.
        old_str:
            Exact existing text to replace. Include enough surrounding
            context so it uniquely identifies one location.
        new_str:
            Replacement text.

    Returns:
        Success or error message.

    Common failures:
        - old_str does not exist.
        - old_str appears multiple times.
        - file cannot be written.

    Best practice:
        Read the file first and copy the exact text into old_str.
        Never guess surrounding context.
    """
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
            f"Error: old_str is not unique in '{filepath}' "
            f"({count} occurrences). Provide more surrounding "
            "context to make it unique. No changes made."
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
    """
    List files in a directory.

    Useful when you know approximately where something is located but
    need to discover filenames.

    Arguments:
        directory:
            Directory to inspect.
        pattern:
            Glob pattern such as:
                "*.py"
                "test_*.py"
                "*.md"

    Returns:
        A list of matching file paths.

    This tool only lists one directory.
    It does not search recursively.
    """
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
    """
    Search the repository for literal text.

    Use this tool to find usages of a symbol, string, error message,
    function call, variable, decorator, import, or constant.

    Arguments:
        pattern:
            Literal text to search for.
        file_pattern:
            Restrict the search to matching files, for example:
                "*.py"
                "test_*.py"
                "*.rst"

    Returns:
        One result per line:

            path:line_number matching source line

    Use this tool when you know what text you are looking for but not
    where it appears.
    """
    if not ALLOWED_DIRECTORIES:
        return "Error: no allowed directories are configured"
    res = []
    for directory in ALLOWED_DIRECTORIES:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__", "node_modules")]
            for file in files:
                if fnmatch.fnmatch(file, file_pattern):
                    f_path = os.path.abspath(os.path.join(root, file))
                    try:
                        with open(f_path, "r", encoding="utf-8") as f:
                            for i, line in enumerate(f, start=1):
                                if pattern in line:
                                    res.append(f"{f_path}:{i} {line.rstrip()}")
                    except (UnicodeDecodeError, PermissionError, OSError):
                        continue

    if not res:
        return (
            f"No matches found for pattern '{pattern}' in files matching "
            f"'{file_pattern}'."
        )

    return "\n".join(res)


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """"
    Locate the definition of a Python function or class.

    This is usually the fastest way to find the implementation that
    should be modified.

    Arguments:
        name:
            Exact function or class name.

    Returns:
        One or more matching definitions formatted as:

            path:line_number definition

    Typical workflow:

        search_function_or_class_definition_in_code(...)
        -> read_file(...)
        -> edit_file(...)
    """
    if not ALLOWED_DIRECTORIES:
        return "Error: no allowed directories are configured"
    res = []
    name = re.sub(r"^(?:class|def)\s+", "", name.strip())
    rgx = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b")

    for directory in ALLOWED_DIRECTORIES:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__", "node_modules")]
            for file in files:
                if fnmatch.fnmatch(file, "*.py"):
                    f_path = os.path.abspath(os.path.join(root, file))
                    try:
                        with open(f_path, "r", encoding="utf-8") as f:
                            for i, line in enumerate(f, start=1):
                                if rgx.search(line):
                                    res.append(f"{f_path}:{i} {line.rstrip()}")
                    except (UnicodeDecodeError, PermissionError, OSError):
                        continue

    if not res:
        return f"No definition found for '{name}'."

    return "\n".join(res)


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> str:
    """
    Find references to a symbol throughout the repository.

    The definition itself is excluded from the results.

    Arguments:
        name:
            Symbol name.
        filepath:
            File containing the definition.
        line:
            Definition line number.

    Returns:
        Every matching usage formatted as:

            path:line_number source line

    Use this tool before changing APIs or function signatures to
    understand how the symbol is used elsewhere.
    """
    if not ALLOWED_DIRECTORIES:
        return "Error: no allowed directories are configured"
    abs_def_path, err = _resolve_and_check(filepath)
    if err:
        return err

    res = []
    pattern = re.compile(rf"\b{re.escape(name)}\b")

    for directory in ALLOWED_DIRECTORIES:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__", "node_modules")]
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
    """
    Execute the benchmark evaluation script.

    This is the primary way to verify that a proposed fix actually
    solves the reported issue.

    Returns:
        Exit code, stdout and stderr from the evaluation script.

    Typical workflow:

        investigate
        -> edit_file(...)
        -> run_tests()

    Never assume a fix is correct without running this tool.

    If the tests fail, inspect the reported errors, modify only the
    necessary code, and run this tool again.
    """
    repo_root = _repository_root()
    if not repo_root:
        return "Error: no allowed directories are configured"
    if not EVAL_SCRIPT_PATH or not os.path.isfile(EVAL_SCRIPT_PATH):
        return f"Error: eval script not found at {EVAL_SCRIPT_PATH}"

    try:
        result = subprocess.run(
            ["bash", EVAL_SCRIPT_PATH],
            cwd=repo_root,
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
        f"--- stdout ---\n{_bounded_output(result.stdout)}\n"
        f"--- stderr ---\n{_bounded_output(result.stderr)}"
    )


@mcp.tool()
def get_patch() -> str:
    """
    Return the Git patch representing every repository modification.

    This should normally be called only after the evaluation tests
    succeed.

    Returns:
        Unified git diff.

    Typical workflow:

        edit_file(...)
        -> run_tests()
        -> get_patch()
        -> final_answer(get_patch())

    If no files were modified, an error is returned.
    """
    repo_root = _repository_root()
    if not repo_root:
        return "Error: no allowed directories are configured"
    try:
        result = subprocess.run(
            ["git", "-c", "core.fileMode=false", "diff"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "Error: git diff timed out"
    except OSError as e:
        return f"Error: could not run git diff: {e}"

    if result.returncode != 0:
        return (
            f"Error: git diff failed (exit {result.returncode}): "
            f"{result.stderr}"
        )

    if not result.stdout.strip():
        return "Error: no changes detected (empty diff)"

    return result.stdout


@mcp.tool()
def run_command(command: str, workdir: str = ".") -> str:
    """
    Execute a shell command inside the repository.

    Use this tool when the required action cannot be accomplished with
    the repository-specific tools.

    Common uses:
        - run a specific pytest command
        - inspect generated files
        - execute project utilities
        - reproduce a bug

    Arguments:
        command:
            Shell command to execute.
        workdir:
            Working directory relative to the repository.

    Returns:
        Exit code, stdout and stderr.

    Prefer run_tests() for benchmark verification.
    Use this tool only when a custom command is required.
    """
    abs_workdir, err = _resolve_and_check(workdir)
    if err:
        return err
    if not os.path.isdir(abs_workdir):
        return f"Error: working directory not found: {workdir}"

    safe, safe_err = _is_safe_command(command)
    if not safe:
        return safe_err or ""

    if not command.strip().startswith(("git", "python", "pytest", "./", "../")):
        return (
            "Error: use the MCP repository tools instead of shell commands for this task. "
            "Prefer read_file, edit_file, run_tests(), and get_patch()."
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=abs_workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after 120s: {command}"
    except OSError as e:
        return f"Error: could not run command: {e}"

    return (
        f"exit_code: {result.returncode}\n"
        f"--- stdout ---\n{_bounded_output(result.stdout)}\n"
        f"--- stderr ---\n{_bounded_output(result.stderr)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"],
                        default="stdio")
    parser.add_argument("--allowed-directory", action="append", default=[])
    parser.add_argument("--eval-script", default="/tmp/eval.sh")
    args = parser.parse_args()

    if not args.allowed_directory:
        parser.error("at least one --allowed-directory is required")
    global ALLOWED_DIRECTORIES
    ALLOWED_DIRECTORIES = tuple(os.path.realpath(path)
                                for path in args.allowed_directory)
    global EVAL_SCRIPT_PATH
    EVAL_SCRIPT_PATH = args.eval_script

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
