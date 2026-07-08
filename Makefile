FILES = client.py server.py
MAIN = main.py
PYTEST_SCRIPT = test_main.py
PY = uv run python3

install:
	uv sync

run:
	$(PY) client.py server.py

test:
	uv run pytest $(PYTEST_SCRIPT)

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
