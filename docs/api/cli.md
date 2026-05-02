# CLI Reference

Metaseed provides a command-line interface built with [Typer](https://typer.tiangolo.com/).

## Installation

The CLI is available after installing the package:

```bash
uv sync
uv run metaseed --help
```

## Commands

### version

Show the package version:

```bash
metaseed version
```

### entities

List available MIAPPE entities for a version:

```bash
metaseed entities --version 1.1
```

### validate

Validate a MIAPPE metadata file:

```bash
metaseed validate <file> --entity investigation --version 1.1
```

### template

Generate an empty template for an entity:

```bash
metaseed template investigation --output my_investigation.yaml --format yaml
```

Options:

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output file path (prints to stdout if not specified) |
| `--format`, `-f` | Output format: `yaml` (default) or `json` |
| `--version`, `-v` | MIAPPE version (default: 1.1) |

### convert

Convert between YAML and JSON formats:

```bash
metaseed convert input.yaml output.json --entity investigation
```

The format is determined by file extension (`.yaml`, `.yml`, or `.json`).

### ui

Launch the web interface:

```bash
metaseed ui --host 127.0.0.1 --port 8080
```

Options:

| Option | Description |
|--------|-------------|
| `--host`, `-h` | Host to bind to (default: 127.0.0.1) |
| `--port`, `-p` | Port to bind to (default: 8080) |

The web interface provides:

- Visual entity browser organized by hierarchy
- Dynamic forms generated from YAML specifications
- Nested entity creation (e.g., add Studies to an Investigation)
- Validation feedback
- Support for both MIAPPE and ISA profiles

### profiles

List available profiles and their versions:

```bash
metaseed profiles
```

Output shows all installed profiles (miappe, isa, jerm, cropxr-phenotyping, etc.) with their available versions.

### compare

Compare multiple profile specifications to see differences in entities, fields, and constraints:

```bash
# Compare two profiles (outputs markdown to stdout)
metaseed compare miappe/1.1 isa/1.0

# Compare with output file
metaseed compare miappe/1.1 isa/1.0 -o comparison.md

# Different output formats
metaseed compare miappe/1.1 isa/1.0 -f csv -o comparison.csv
metaseed compare miappe/1.1 isa/1.0 -f html -o comparison.html

# Compare multiple profiles
metaseed compare miappe/1.1 isa/1.0 cropxr-phenotyping/0.0.5
```

Options:

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output file path (prints to stdout if not specified) |
| `--format`, `-f` | Output format: `markdown` (default), `csv`, or `html` |

The comparison report shows:

- Summary statistics (total entities, common, unique, modified, conflicts)
- Entity-by-entity comparison with presence indicators
- Field-level differences including type changes and constraint modifications

### merge

Merge multiple profile specifications into a single combined profile:

```bash
# Basic merge (uses first_wins strategy)
metaseed merge miappe/1.1 isa/1.0 -o combined.yaml

# Merge with specific strategy
metaseed merge miappe/1.1 cropxr-phenotyping/0.0.5 -s most_restrictive -o strict.yaml

# Custom name and version
metaseed merge miappe/1.1 isa/1.0 -n my-profile -v 2.0 -o my-profile.yaml
```

Options:

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output YAML file path (default: merged.yaml) |
| `--strategy`, `-s` | Merge strategy (default: first_wins) |
| `--name`, `-n` | Name for the merged profile |
| `--version`, `-v` | Version for the merged profile (default: 1.0) |

Available merge strategies:

| Strategy | Behavior |
|----------|----------|
| `first_wins` | Use the first profile's value for conflicts |
| `last_wins` | Use the last profile's value for conflicts |
| `most_restrictive` | required=True wins, tighter constraints |
| `least_restrictive` | required=False wins, looser constraints |
| `prefer_<profile>` | Always prefer a specific profile (e.g., `prefer_miappe/1.1`) |

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--help` | Show help message and exit |

## Configuration

The CLI reads configuration from:

1. Command-line arguments
2. Environment variables (prefixed with `METASEED_`)
3. Configuration file (`metaseed.yaml` in current directory)
