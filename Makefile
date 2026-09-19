PYTHON ?= python3

.PHONY: test test-stdlib lint typecheck build eval demo serve clean

test:
	$(PYTHON) -m pytest -q

test-stdlib:
	$(PYTHON) -m unittest discover -s tests -v

lint:
	ruff check src eval demo tests || $(PYTHON) -m ruff check src eval demo tests

typecheck:
	mypy src || $(PYTHON) -m mypy src

build:
	$(PYTHON) -m build 2>/dev/null || $(PYTHON) -m compileall -q src eval demo tests && echo "build check: compileall OK"

eval:
	$(PYTHON) -m eval.harness --out eval/eval-results.json --report eval/REPORT.md

demo:
	$(PYTHON) -m demo.demo

serve:
	$(PYTHON) -m adaptive_gateway --port $${PORT:-8080}

clean:
	rm -rf build dist *.egg-info src/*.egg-info __pycache__ .mypy_cache .ruff_cache .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
