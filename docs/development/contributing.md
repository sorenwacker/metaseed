# Contributing

Guidelines for contributing to Metaseed.

## Development Setup

1. Clone the repository:

    ```bash
    git clone <repository-url>
    cd metaseed
    ```

2. Install dependencies and pre-commit hooks:

    ```bash
    make dev
    ```

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
uv run pytest tests/test_version.py
```

### Code Quality

Pre-commit hooks run automatically on commit. To run manually:

```bash
# Run all hooks
uv run pre-commit run --all-files

# Run ruff linter only
make lint

# Format code
make format
```

### Documentation

```bash
# Serve docs locally
make docs-serve

# Build docs
make docs
```

## Code Style

- Follow [PEP 8](https://pep8.org/) conventions
- Use [Google style docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- Maximum line length: 100 characters
- Use type hints for all function signatures

## Commit Messages

- Use present tense ("add feature" not "added feature")
- Keep the first line under 72 characters
- Reference issues where applicable

## Pull Requests

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all tests pass
4. Update documentation if needed
5. Submit a pull request

## Project Structure

```
metaseed/
├── src/metaseed/       # Main package
│   ├── api/            # FastAPI routes
│   ├── cli/            # Typer commands
│   ├── core/           # Shared utilities
│   ├── models/         # Pydantic models
│   ├── specs/          # YAML schemas
│   ├── storage/        # Persistence
│   └── validators/     # Validation logic
├── tests/              # Test suite
└── docs/               # Documentation
```

## Exception Handling

Metaseed uses two exception hierarchies. Use the correct one based on where your code lives.

| Layer | Base Class | Module | When to Use |
|-------|------------|--------|-------------|
| Internal | `MiappeError` | `core/exceptions.py` | Code in `core/`, `models/`, `specs/`, `storage/` |
| Public API | `MetaseedError` | `api/errors.py` | Code in `api/`, user-facing errors |

Internal exceptions are caught at the API boundary and translated to public exceptions. See [Exception Architecture](../architecture/exceptions.md) for details.
