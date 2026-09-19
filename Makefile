.PHONY: test test-stdlib lint typecheck build eval demo serve clean

test:
	python -m pytest -q

test-stdlib:
	python -m unittest discover -s tests -v

lint:
	ruff check src eval demo tests || python -m ruff check src eval demo tests

typecheck:
	mypy src || python -m mypy src

build:
	python -m build 2>/dev/null || python -m compileall -q src eval demo tests && echo "build check: compileall OK"

eval:
	python -m eval.harness --out eval/eval-results.json --report eval/REPORT.md

demo:
	python -m demo.demo

serve:
	python -m adaptive_gateway --port $${PORT:-8080}

clean:
	rm -rf build dist *.egg-info src/*.egg-info __pycache__ .mypy_cache .ruff_cache .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
