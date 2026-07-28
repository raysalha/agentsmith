FILES = mcp_tools_mbpp.py mcp_tools_swebench.py \
		agent_swebench/*.py \
		agent_mbpp/*.py

PY = uv run python3 -m

install:
	uv sync

run_mbpp:
	clear
	$(PY) agent_mbpp \
		--task-file mbpp_tasks/809.json \
		--output mbpp_solution.json \
		--model-name openrouter/free \
		--provider-url https://openrouter.ai/api/v1 \
		--target mcp_tools_mbpp.py

run_swebench:
	clear
	$(PY) agent_swebench \
		--task-file swebench_task.json \
		--output swebench_solution.json \
		--model-name openrouter/free \
		--provider-url https://openrouter.ai/api/v1 \
		--target mcp_tools_swebench.py

debug:
	$(PY) -m pdb agent_mbpp

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache

lint:
	clear
	$(PY) flake8 $(FILES)
	$(PY) mypy $(FILES) --warn-return-any \
		--warn-unused-ignores \
		--ignore-missing-imports \
		--disallow-untyped-defs \
		--check-untyped-defs

lint-strict:
	$(PY) -m flake8 $(FILES)
	$(PY) -m mypy $(FILES) --strict
