.PHONY: install dev test test-ui test-cov lint format docs docs-serve ui clean help

help:
	@echo "Available targets:"
	@echo "  install    - Install dependencies"
	@echo "  dev        - Install dev + docs dependencies and pre-commit hooks"
	@echo "  test       - Run tests (excluding UI tests)"
	@echo "  test-ui    - Run UI tests (requires Chrome)"
	@echo "  test-cov   - Run tests with coverage"
	@echo "  lint       - Run linter"
	@echo "  format     - Format code"
	@echo "  docs       - Build documentation"
	@echo "  docs-serve - Serve documentation locally"
	@echo "  ui         - Launch web interface"
	@echo "  clean      - Remove build artifacts"

install:
	uv sync

dev:
	uv sync --extra dev --extra docs
	uv run pre-commit install

test:
	uv run pytest -m "not ui"

test-ui:
	uv run pytest -m ui

test-cov:
	uv run pytest --cov --cov-report=term-missing

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

docs:
	uv run mkdocs build

docs-serve:
	uv run mkdocs serve

ui:
	uv run miappe ui

clean:
	rm -rf .pytest_cache .coverage htmlcov site build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
