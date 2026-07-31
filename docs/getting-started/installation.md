# Installation

## Requirements

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager

## Install from Source

```bash
git clone <repository-url>
cd metaseed
make install
```

## Development Installation

```bash
make dev
```

This installs dev dependencies (pytest, ruff, pre-commit) and docs dependencies (MkDocs).

## Verify Installation

```bash
uv run metaseed version
make test
```

## Upgrading

### Upgrading to 0.22

0.22 requires a profile spec's `version` to be `MAJOR.MINOR` (see [Profile Versioning](../api/schema-specs.md#profile-versioning)). Specs already on disk can violate the rule — earlier releases minted versions such as `1.2-dev-a1b2c3` when a template was cloned — and such a spec is still listed by `metaseed profiles` but fails to load.

After upgrading, check for affected specs and repair them:

```bash
uv run metaseed migrate-specs           # report only
uv run metaseed migrate-specs --apply   # rewrite the version values
```

The command reports anything it will not repair on its own rather than guessing; see [`migrate-specs`](../api/cli.md#migrate-specs).
