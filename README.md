# *This project has been created as part of the 42 curriculum by [rsalha](https://profile-v3.intra.42.fr/users/rsalha) & [monasser](https://profile-v3.intra.42.fr/users/monasser).*

# Agent Smith — Autonomous Coding Agent

## Description

**Agent Smith** is an agentic framework that autonomously solves coding challenges by writing Python code, executing it in a sandboxed environment, observing the real results, and iterating until a solution is found. Instead of classical JSON-based tool calling, the agent generates executable **Python code** (a "code-based tool calling" approach), which is run inside a restricted, process-isolated sandbox that exposes tools discovered dynamically from a connected MCP (Model Context Protocol) server.

The framework is applied to two benchmarks:

* **MBPP** — self-contained algorithmic Python problems.
* **SWE-bench** — real bug-fixing tasks inside Dockerized repository checkouts.

The agent operates through a structured `Thought → Code → Observation` loop: the LLM reasons about the task, emits one Python code block, the sandbox executes it and returns the real output, and the loop repeats until the agent calls `final_answer(...)` or a hard limit (iterations / tokens / time) is reached.

## Instructions

### Requirements

* Python 3.10+
* [`uv`](https://docs.astral.sh/uv/) as package manager
* Docker (for SWE-bench tasks only)
* An OpenRouter (or other OpenAI-compatible) API key

### Setup

```bash
uv sync
```

Create a `.env` file at the repo root with at least:

```
OPENROUTER_API=sk-or-...,sk-or-...   # comma-separated for multi-key rotation
AGENTSMITH_MODELS=poolside/laguna-s-2.1:free,google/gemma-4-26b-a4b-it:free,...
```

### Running the sandbox standalone (manual testing)

```bash
uv run sandbox
uv run sandbox sandbox_template.json
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
uv run sandbox --mcp-server <URL>
```

This drops into an interactive prompt: type Python code (blank line to submit), and see exactly what the sandbox returns — the same execution path the real agent uses, without needing an LLM in the loop.

### Running the MBPP agent

```bash
# 1. Dump a task (via the moulinette)
cd moulinette
uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json

# 2. Run the agent
cd ../student
uv run python -m agent_mbpp \
    --task-file ../cache/mbpp_task.json \
    --output ../cache/mbpp_solution.json \
    --model-name "poolside/laguna-s-2.1:free" \
    --provider-url "https://openrouter.ai/api/v1" \
    --target mcp_tools_mbpp.py

# 3. Validate
cd ../moulinette
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json ../cache/mbpp_solution.json
```

If `--model-name` is omitted, one is picked automatically from the configured model pool (`helper/models.py`).

### Running the SWE-bench agent

```bash
cd moulinette
uv run moulinette_eval dump swebench --output ../cache/swebench_task.json

cd ../student
uv run python -m agent_swebench \
    --task-file ../cache/swebench_task.json \
    --output ../cache/swebench_solution.json \
    --model-name "poolside/laguna-s-2.1:free" \
    --provider-url "https://openrouter.ai/api/v1" \
    --target mcp_tools_swebench.py

cd ../moulinette
uv run moulinette_eval validate swebench ../cache/swebench_task.json ../cache/swebench_solution.json
```

`agent_swebench`'s entry point automatically pulls the task's `docker_image`, copies `/testbed` out to a local working directory (`/tmp/agent`), and starts a persistent container mounting that directory before the agent loop begins. The container is removed automatically in `cleanup()` once the run finishes (or on `Ctrl+C`).

## Resources

* [Model Context Protocol specification](https://modelcontextprotocol.io/)
* [SWE-bench](https://www.swebench.com/) / [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)
* [MBPP dataset](https://github.com/google-research/google-research/tree/master/mbpp)
* [OpenRouter API documentation](https://openrouter.ai/docs)
* Python `multiprocessing`, `resource`, and `contextlib.redirect_stdout` standard library documentation (used to build the sandbox's process isolation)
* Pydantic v2 documentation (used for all configuration and I/O data models)
* MCP Server: (https://modelcontextprotocol.io/docs/develop/build-server#system-requirements)


### AI usage disclosure

An AI assistant (Claude) was used throughout this project as a coding partner:

* Explaining the subject's architecture requirements and clarifying the boundary between the sandbox's execution restrictions and the MCP tool layer's real filesystem/process access.
* Reviewing and debugging the sandbox implementation (subprocess isolation, timeout/memory enforcement, tool-call proxying over pipes) across several iterations.
* Reviewing the orchestrator, MCP tool servers, and CLI entry points for bugs (e.g. missing environment variable ordering, unenforced token budgets, message-role inconsistencies).
* Drafting the system prompts used to instruct the LLM on the required `Thought` / single-Python-code-block response format.
* Assembling `BENCHMARK_REPORT.md` from raw run logs.

All architectural decisions (subprocess vs. thread-based sandboxing, MCP server placement relative to Docker, model-rotation strategy, etc.) were made and understood by the author(s); AI-suggested code was reviewed, tested, and adapted rather than used unmodified.

---

## System Architecture

```
LLM API  <-->  Orchestrator  -->  Code Extraction  -->  Sandbox (subprocess)
                                                            |
                                                     tool_call over pipe
                                                            |
                                                        Sandbox.run()
                                                    (parent process, owns
                                                     the live MCP session)
                                                            |
                                                       MCP Client/Session
                                                            |
                                                  MCP Server (mcp_tools_*.py)
                                                    (stdio or streamable HTTP)
```

**Key components:**

* **`helper/orchestrator.py` — `Orchestrator`**: the central agent loop. Calls the LLM (`create_completion`, with retry/backoff and multi-key/multi-model rotation on rate limits), validates the response's protocol (`response_protocol_error`), extracts the Python code block (`extract_python_code`), sends it to the sandbox, and records per-step metrics.
* **`helper/sandbox.py` — `Sandbox`**: the execution boundary. Spawns a fresh, isolated subprocess per code block, enforces a real timeout and memory limit, and proxies any tool call the code makes back to the parent process over a `multiprocessing.Pipe`.
* **`helper/client.py` — `MCPClient`**: owns the live MCP session (stdio or streamable HTTP transport) and performs the actual `call_tool` requests on behalf of the sandbox.
* **`mcp_tools_mbpp.py` / `mcp_tools_swebench.py`**: standalone MCP servers exposing the actual tool implementations, with real (unsandboxed) filesystem/process access, scoped to the task's working directory.
* **`helper/data_models.py`**: Pydantic models for all configuration and I/O — `SandboxConfig`, `MBPPTaskInput`, `SWEBenchTaskInput`, `StepMetrics`, `SolutionOutput`.
* **`helper/models.py`**: manages the pool of usable free-tier models and provides automatic fallback candidates if a model is rate-limited or unusable.
* **`agent_mbpp/` / `agent_swebench/` `system_prompt.py`**: builds the system prompt dynamically from the connected MCP server's tool schemas (tool names, parameters, descriptions) and the sandbox's configured import allowlist.

## Agent Loop Explanation

Each task is processed by `Orchestrator.process_query()` as a loop of up to `MBPP_MAX_TURN` (10) or `SWEBENCH_MAX_TURN` (30) iterations:

1. **Call the LLM** with the running message history (`create_completion`), with automatic retry on transient errors, API-key rotation on HTTP 429, and model rotation as a last resort if the current model is exhausted or unusable.
2. **Validate the response's protocol** (`response_protocol_error`): rejects responses with no Python code block, more than one, an empty provider response, or safety-metadata-only output — the sandbox/orchestrator always tells the model *why* a response was rejected and re-prompts with the exact required format, rather than silently failing.
3. **Extract the Python code** (`extract_python_code`) — primarily from fenced ` ```python ` blocks, with a fallback JSON-embedded-string extractor for models that wrap code differently.
4. **Execute the code in the sandbox** (`sandbox.run(code)`), which returns an object with `output` (captured stdout), `final_answer` (set only if the code called `final_answer(...)`), and `error`.
5. **Validate `final_answer` for SWE-bench**: a raw `is_valid_patch()` check rejects false-positive "successes" where `get_patch()` actually returned an error string (e.g. "no changes detected") instead of a real diff.
6. **Record `StepMetrics`** (tokens, timing, retries, raw LLM output, sandbox input/output) for every iteration, feeding directly into the final `SolutionOutput`.
7. **Terminate** either on a valid `final_answer`, on exhausting the iteration budget, or on an unrecoverable error — in all cases a `SolutionOutput` (`solution.json`) is produced.

## Sandbox Design

The sandbox's job is narrow and specific: **safely execute the LLM's own Python glue code** (its reasoning/orchestration logic), not the tools it calls. Tool implementations (real file I/O, `run_command`, Docker-bridged operations) run entirely outside the sandbox, in the separate MCP server process, with real privileges scoped to the task's working directory.

* **Process isolation**: `Sandbox.run()` spawns a fresh subprocess (`multiprocessing.get_context("spawn")`) per code block via `_execute_in_child`. This is what makes the timeout and memory limit *real* — a hung or malicious code block is killed outright (`process.terminate()`), not merely abandoned, which is not achievable with a thread-based approach since Python cannot forcibly terminate a running thread.
* **Import restriction**: `safe_import()` replaces `__import__` in the child's builtins with an allowlist check (`SandboxConfig.authorized_imports`), supporting both exact module names and wildcard prefixes (e.g. `"typing.*"`).
* **Builtin restriction**: only a small, explicit set of builtins (`AUTHORIZED_BUILTINS`) is exposed — no `open`, `eval`, `exec`, or raw `__import__`, so the sandboxed code has no path to the real filesystem or process table except through the injected tool wrappers.
* **Memory limit**: `resource.setrlimit(RLIMIT_AS, ...)` is applied inside the child process only, so it constrains just that one execution, not the whole orchestrator.
* **Timeout**: enforced by the parent (`asyncio.wait_for(..., timeout=self.max_exec_time)`); on timeout the child process is forcibly terminated.
* **Tool-call proxying**: tool wrapper functions injected into the child's namespace don't perform any real work themselves — they serialize `(tool_name, kwargs)` and send it over a `multiprocessing.Pipe` to the parent, which is the only process holding the live, async MCP session. The parent awaits `session.call_tool(...)` and sends the result back across the pipe, so the child sees an ordinary synchronous function call.
* **`final_answer(...)`**: not an MCP tool — it's a sandbox-native construct. Calling it raises an internal `FinalAnswer` exception, caught in the child and relayed to the parent as the loop's termination signal.
* **Exception propagation**: `KeyboardInterrupt` and `SystemExit` are explicitly re-raised rather than caught, so the process can still be interrupted/shut down cleanly.
* **Explicit failure feedback**: no-code-block, malformed-response, and execution-error cases are always surfaced back to the LLM as an explicit `Sandbox output: ERROR: ...` message rather than being silently swallowed, so the model is never left guessing about what happened.

## Tool Implementation Details

MCP tools are implemented in two standalone server files, both runnable over stdio or streamable HTTP, and discovered dynamically by the sandbox at connection time (`Sandbox.init_mcp_client`) — tool wrappers and the system prompt's tool documentation are generated from whatever tools the connected server actually advertises.

**`mcp_tools_swebench.py`** exposes the full mandatory tool set for repository-level work:

* File system: `read_file`, `edit_file`, `insert_after`, `list_files`
* Code search: `search_code`, `search_function_or_class_definition_in_code`, `find_references`
* Execution: `run_tests`, `get_patch`, `run_command`

**`mcp_tools_mbpp.py`** exposes the single mandatory tool for self-contained algorithmic tasks:

* `run_tests(code)` — executes the candidate solution against the task's configured `IMPORTS`/`TESTS`, capturing stdout and per-test tracebacks, and returns a human-readable pass/fail report (e.g. *"Passed 3/5 tests... All tests passed, you can now run final_answer()"*), so the agent always gets clear, actionable feedback rather than a bare boolean.

For SWE-bench, the MCP server operates against a per-task working directory (`/tmp/agent`, bind-mounted into the task's Docker container at `/testbed`), so tool actions are real (genuinely mutate the checked-out repository, letting `get_patch()` produce a real `git diff`) but scoped to that single task's disposable environment.

## Benchmark Results and Analysis

Model and task comparisons, provider reliability, exploration-efficiency/submission-discipline metrics, and an ablation study are documented in **[`BENCHMARK_REPORT.md`](./BENCHMARK_REPORT.md)**, backed by the raw `solution.json` outputs of each run included in this repository.

**Summary**: `poolside/laguna-s-2.1:free` was selected as the primary model — across 11 validated SWE-bench runs it was the only model producing syntactically valid, applicable patches (55% validated pass rate), while every other tested model (the `nvidia/nemotron-*` family, `google/gemma-4-26b-a4b-it:free`, and the `openrouter/free` auto-router) failed every validated run in this batch, largely due to non-Python tool-call format drift, daily rate-limit exhaustion, or invalid patch output. The report also documents meaningful run-to-run variance for the same model/task pair, which is discussed as an open risk rather than smoothed over.
