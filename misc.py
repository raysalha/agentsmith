RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
RESET = "\033[0m"

NO_CODE_BLOCK = """Sandbox output:
ERROR: Your previous response violated the required protocol.
Reason: No Python code block was found.

You must reply using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""

MORE_THAN_ONE_CODE_BLOCK = """Sandbox output:
ERROR: Your previous response violated the required protocol.
Reason: More than one Python code block was generated.

Reply again using EXACTLY this format:

Thought:
<one sentence describing why the next action is needed>

```python
# python code only
```"""
