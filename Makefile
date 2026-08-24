.PHONY: install setup test test-ui test-cov demo test-export test-validation lint typecheck format docs docs-build ui dev clean help

help:
	@echo "Available targets:"
	@echo "  install         - Install dependencies"
	@echo "  setup           - Install dev + docs dependencies and pre-commit hooks"
	@echo "  dev             - Run web UI with hot reload (for development)"
	@echo "  test            - Run tests (excluding UI tests)"
	@echo "  test-ui         - Run UI tests (requires Chrome)"
	@echo "  test-cov        - Run tests with coverage"
	@echo "  demo            - Run demo test creating all MIAPPE entities (visible browser)"
	@echo "  test-export     - Run Excel export tests (visible browser)"
	@echo "  test-validation - Run validation UI tests (visible browser)"
	@echo "  lint            - Run linter"
	@echo "  typecheck       - Run mypy strict type checking"
	@echo "  format          - Format code"
	@echo "  docs            - Serve documentation locally with hot reload"
	@echo "  docs-build      - Build documentation"
	@echo "  ui              - Launch web interface"
	@echo "  clean           - Remove build artifacts"

install:
	uv sync

setup:
	uv sync --extra dev --extra docs
	uv run pre-commit install

# The marker set must match CI (.github/workflows/ci.yml): network tests hit
# live third-party APIs and are not part of the local default either — one of
# them (test_example_accessions.py) also poisons the model caches for later
# tests when it runs, which "-m not ui" let happen.
test:
	uv run pytest -m "not ui and not selenium and not network"

test-ui:
	uv run pytest -m ui

test-cov:
	uv run pytest --cov --cov-report=term-missing

demo:
	uv run pytest tests/test_ui/test_selenium.py::TestCreateAllEntityTypes::test_create_all_entities -v

test-export:
	uv run pytest tests/test_ui/test_selenium.py::TestExcelExport -v

test-validation:
	uv run pytest tests/test_ui/test_selenium.py::TestValidation -v

lint:
	uv run ruff check src tests

typecheck:
	uv run python -m mypy src/metaseed

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

docs:
	uv run python -m mkdocs serve --livereload

docs-build:
	uv run python -m mkdocs build

ui:
	uv run metaseed ui

dev:
	# --reload-dir scopes the watcher to the source. Without it uvicorn
	# watches the whole working tree, which here is 664 MB.
	uv run python -m uvicorn metaseed.ui.app:app --host 127.0.0.1 --port 8765 --reload --reload-dir src

clean:
	rm -rf .pytest_cache .coverage htmlcov site build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
