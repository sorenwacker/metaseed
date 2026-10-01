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

A push runs the fast core of the suite before it leaves the machine (`scripts/pre_push_tests.py`: the specification language, validators, models, facade, API and services — about 1,700 tests in a few seconds), plus the duplicate-code check. The pull request's CI runs the whole suite and is the gate for merging, so the full fifteen-minute run is not paid twice per push. A push of a release tag runs the full suite locally, because nothing downstream checks a tag before it is published; `METASEED_PUSH_FULL=1 git push` asks for the full suite on any push. Prefer that to `--no-verify`, which disables every hook. `tests/test_pre_push_runs_the_core_not_the_suite.py` pins this.

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

Exceptions API consumers must catch inherit from `MetaseedError` in `api/errors.py`; modules below the API define their own exceptions locally, and the API layer translates them at its boundary. See [Exceptions](../architecture/exceptions.md) for details.

## Where Renovate runs

Renovate runs from this repository's own workflow, `.github/workflows/renovate.yml`: weekly (early Monday, UTC) and on demand from the Actions tab (**Renovate > Run workflow**), reading `renovate.json`. The hosted Mend app is installed but has never run on this repository; a workflow here has a visible log and needs nothing enabled elsewhere.

The workflow needs one secret, `RENOVATE_TOKEN`: a fine-grained personal access token for this repository with read and write access to *Contents*, *Pull requests*, *Issues*, and *Workflows*. It can't use the workflow's own `GITHUB_TOKEN`, because pull requests opened with that token trigger no other workflows — the CI gate would never run on an update and nothing could auto-merge. If the hosted app starts running as well, disable one of the two, or every update arrives twice.

## Where the fresh-install smoke test runs

`.github/workflows/fresh-install-smoke.yml` builds the wheel from the commit, installs it into a clean environment with a fresh dependency resolution and all feature extras, and runs the entry points and the imports users hit first. The locked test suite cannot see a dependency bound that resolves to a breaking upstream release; this job can, and it caught one. It runs in three places: before publishing a release (`release.yml`, which gates `publish` on it), on every pull request that changes `pyproject.toml` or `uv.lock`, and weekly (`smoke.yml`), because a new upstream release can break a bound nobody touched. `tests/test_the_fresh_install_smoke_does_not_wait_for_a_release.py` pins all three.
