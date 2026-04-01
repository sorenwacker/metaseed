# Metaseed

Schema-driven metadata management from YAML specifications.

## Overview

Metaseed provides tools for creating, editing, and validating structured metadata from schema specifications.

### Features

- **Schema-driven**: YAML specifications define metadata structures
- **Ontology-backed**: Reference external ontologies via URIs
- **Factory pattern**: Dynamically generates Pydantic models from specs
- **Multiple interfaces**: REST API (FastAPI), CLI (Typer), and web UI (HTMX)
- **Validation**: Composable validation rules from schema definitions

## Capabilities

### What Metaseed Can Do

- Define entity schemas in YAML with nested tree structures
- Generate Pydantic models dynamically from specs
- Validate with composable rules (patterns, ranges, enums, conditionals, cross-field)
- Serialize to JSON/YAML
- Serve via REST API, CLI, or Python API
- Support multiple schema versions

### What Metaseed Cannot Do

- Arbitrary graph relationships (trees only)
- Database storage (file-based only)
- Binary/blob types, maps with arbitrary keys, union types
- Custom code execution in validation
- Query/search/filter operations
- Export to CSV, XML, Excel

## Installation

Requires Python 3.11+ and [UV](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/sorenwacker/metaseed.git
cd metaseed

# Install dependencies
uv sync --extra dev --extra docs
```

## Development

```bash
# Setup development environment
make dev

# Run tests
make test

# Run linter
make lint

# Format code
make format

# Serve documentation locally
make docs-serve
```

Run `make help` to see all available targets.

## Architecture

```
metaseed/
├── src/metaseed/
│   ├── specs/        # YAML schema specifications
│   ├── models/       # Generated Pydantic models
│   ├── validators/   # Validation logic
│   ├── storage/      # Persistence layer
│   ├── api/          # FastAPI REST endpoints
│   ├── cli/          # Typer CLI commands
│   └── core/         # Shared utilities
├── tests/            # Test suite
└── docs/             # MkDocs documentation
```

## License

MIT
