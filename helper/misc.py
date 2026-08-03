MBPP_MAX_TURN = 10
MBBP_MAX_INPUT_TOKEN = 6000
MBBP_MAX_OUTPUT_TOKEN = 1500
MBPP_TIMEOUT = 120

SWEBENCH_MAX_TURN = 30
SWEBENCH_MAX_INPUT_TOKEN = 300000
SWEBENCH_MAX_OUTPUT_TOKEN = 10000
SWEBENCH_TIMEOUT = 900

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
RESET = "\033[0m"

NO_CODE_BLOCK = """
ERROR: Your previous response violated the required protocol.
Reason: No Python code block was found.

You must reply using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

EMPTY_LLM_RESPONSE = """
ERROR: The provider returned an empty response.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

EMPTY_SANDBOX_OUTPUT = ("Sandbox output is empty. did you forget to print the "
                        "tool result?")

MORE_THAN_ONE_CODE_BLOCK = """
ERROR: Your previous response violated the required protocol.
Reason: More than one Python code block was generated.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

INVALID_RESPONSE_FORMAT = """
ERROR: Your previous response violated the required protocol.
Reason: The response must contain only a Thought section followed by exactly
one Python code block, with no text before Thought and no text after the
closing code fence.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

SAFETY_MSG = ("Your previous response was provider safety metadata, not an "
              "agent response. Do not output safety labels; follow the "
              "required Thought and single Python code-block format.")

MAX_TURN_ERROR = "Unable to complete the task within the tool-turn limit."

EXIT_ERROR = "Sandbox process exited unexpectedly"

NO_GITPATCH = "Final answer was not a non-empty git patch."
