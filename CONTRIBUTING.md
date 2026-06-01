# Contributing to Metaseed

Thank you for your interest in contributing to Metaseed. This document provides guidelines for contributing.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) for dependency management

### Setup

```bash
# Clone the repository
git clone https://github.com/sorenwacker/metaseed.git
cd metaseed

# Install dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

### Running the Application

```bash
# Start the web UI
make dev

# Start documentation server
make docs
```

## Code Style

- **Formatter**: ruff (enforced by pre-commit)
- **Linter**: ruff
- **Type hints**: Required for all public functions
- **Docstrings**: Google style
- **Max file length**: 1000 lines

### Pre-commit Hooks

The repository uses pre-commit hooks to enforce code quality:

```bash
# Run hooks manually
uv run pre-commit run --all-files
```

## Testing

All changes must include tests. We use pytest.

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_validators/test_rules.py

# Run with coverage
uv run pytest --cov=metaseed
```

### Test Guidelines

- Write unit tests for new functionality
- Update existing tests when modifying behavior
- Aim for meaningful coverage, not 100%

## Pull Request Process

1. **Fork** the repository
2. **Create a branch** from `main` with a descriptive name
3. **Make changes** following the code style guidelines
4. **Write tests** for new functionality
5. **Run tests** locally to ensure they pass
6. **Commit** with clear, concise messages
7. **Push** to your fork
8. **Open a PR** against `main`

### PR Requirements

- All tests pass
- Pre-commit hooks pass
- Clear description of changes
- Link to related issues (if applicable)

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Reference issues when relevant

## Reporting Issues

### Bug Reports

Include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Python version and OS
- Relevant error messages

### Feature Requests

Include:
- Use case description
- Proposed solution (if any)
- Alternatives considered

## Documentation

Documentation lives in `docs/` and uses MkDocs with Material theme.

```bash
# Preview docs locally
make docs
```

When adding features:
- Update relevant documentation
- Add docstrings to new functions/classes
- Include examples where helpful

## Questions

Open an issue for questions about contributing or the codebase.
