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

NO_CODE_BLOCK = """ERROR: Your previous response violated the required protocol.
Reason: No Python code block was found.

You must reply using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

MORE_THAN_ONE_CODE_BLOCK = """ERROR: Your previous response violated the required protocol.
Reason: More than one Python code block was generated.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

INVALID_XML = """ERROR: Your previous response violated the required protocol.
Reason: Invalid XML block in <invoke>.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```

OR

Thought:
<one sentence describing why the next action is needed>

<invoke name="read_file">
    <parameter name="filepath">./src/example.py</parameter>
    <parameter name="start_line">1</parameter>
    <parameter name="end_line">20</parameter>
</invoke>"""

INVALID_JSON = """ERROR: Your previous response violated the required protocol.
Reason: Invalid JSON block in <tool_call>.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```

OR

Thought:
<one sentence describing why the next action is needed>

<tool_call>
{
    "name": "read_file",
    "arguments": {
        "filepath": "./src/file.py",
        "start_line": 1,
        "end_line": 20
    }
}
</tool_call>"""

SAFETY_MSG = ("Your previous response was provider safety metadata, not an "
              "agent response. Do not output safety labels; follow the "
              "required Thought and single Python code-block format.")

MAX_TURN_ERROR = "Unable to complete the task within the tool-turn limit."

EXIT_ERROR = "Sandbox process exited unexpectedly"
