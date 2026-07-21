FILES = client.py server.py
MAIN = main.py
PY = uv run python3

install:
	uv sync

run:
	clear
	$(PY) main.py \
		--task-file mbpp_task.json \
		--output solution.json \
		--model-name openrouter/free \
		--provider-url https://openrouter.ai/api/v1 \
		--target mcp_tools_mbpp.py

test:
	uv run pytest

debug:
	$(PY) -m pdb $(MAIN)

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache

lint:
	$(PY) -m flake8 $(FILES)
	$(PY) -m mypy . --warn-return-any \
		--warn-unused-ignores \
		--ignore-missing-imports \
		--disallow-untyped-defs \
		--check-untyped-defs

lint-strict:
	$(PY) -m flake8 $(FILES)
	$(PY) -m mypy . --strict
