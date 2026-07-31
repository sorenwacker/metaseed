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

Output shows all installed profiles (miappe, isa, jerm, darwin-core, dissco, ena, etc.) with their available versions.

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
metaseed compare miappe/1.1 isa/1.0 jerm/1.0
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
metaseed merge miappe/1.1 jerm/1.0 -s most_restrictive -o strict.yaml

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

### check

Validate a dataset with cross-entity reference-integrity checking (stricter than
`validate`, which checks a single entity).

```bash
metaseed check dataset.json
```

### example

Export the example dataset bundled with a profile.

```bash
metaseed example miappe
```

### mcp

Start the MCP (Model Context Protocol) server, exposing metaseed's tools to an
MCP client.

```bash
metaseed mcp
```

### migrate

Migrate stored datasets to use `unique_id` for entity references.

```bash
metaseed migrate
```

### migrate-specs

Repair profile specs whose `version` is not `MAJOR.MINOR`. Since 0.22 a `version` that does not match `^\d+\.\d+$` is rejected on load (see [Profile Versioning](schema-specs.md#profile-versioning)), so a spec written by an earlier release is listed but cannot be loaded. This command finds those files and rewrites the offending value.

```bash
# Report what would change; writes nothing (default)
metaseed migrate-specs

# Write the changes
metaseed migrate-specs --apply
```

Both the built-in specs directory and the user specs directory (`~/.local/share/metaseed/specs/`) are scanned.

#### Normalization rules

The rules combine: in `v1.2.3-rc1` the `v` is stripped, the `-rc1` suffix dropped and the third component truncated, giving `1.2` (LOSSY).

| Stored `version` | Rule | Result |
|------------------|------|--------|
| `'1.2'` | already `MAJOR.MINOR` | unchanged, not reported as a change |
| `v1.2` | a leading `v` is not part of the version | `'1.2'` |
| `1` | a single integer names a MAJOR only; MINOR is `0` | `'1.0'` |
| `1.2-dev-a1b2c3`, `1.2-rc1`, `1.2+build.5` | a pre-release or build suffix is not a profile version component | `'1.2'` |
| `1.2.3` | only two components exist; the rest is discarded | `'1.2'`, reported **LOSSY** |
| `1.0` unquoted | YAML reads it as a number, and `version` is a string | `'1.0'` |
| `draft`, `latest`, `` (empty) | no leading integer, so no version is derivable | unchanged, reported **NEEDS MANUAL FIX** |

The value is always written quoted, which is also what `SpecBuilder.to_yaml()` produces. That is what the unquoted-number row is about: `version: 1` is an integer to YAML and `version: 1.0` a float, and a `version` that is not a string fails to load for that reason alone, digits notwithstanding.

`1.2.3 -> 1.2` is flagged LOSSY because the patch component is discarded: two files that differed only in patch normalize to the same version, and nothing records which was which. A value with no leading integer is never guessed — the file is left alone and the report names it, its path, and the rule it failed.

#### What is written

Only the `version:` value is rewritten. The rest of the file — key order, comments, quoting, blank lines — is left byte-for-byte as it was, so a hand-maintained spec survives the migration unchanged apart from that one value.

A spec's version is also its directory name (`specs/<name>/<version>/profile.yaml`), and `metaseed profiles` and the loader address a spec by that directory name. When the directory name is the same non-conforming string as the file's `version`, it is renamed alongside the value, so the repaired spec is addressable by the version it declares. When the directory name and the declared version already disagree, the directory is left alone and the report notes the mismatch; renaming it would change the version users address the spec by.

A saved dataset records the profile version it was created against, and that reference is not rewritten here. After a rename, edit the `version` field of any dataset naming the old string — the report says so whenever it renames anything.

#### Collisions

A rename is refused, not resolved, when it would put two specs at the same `<name>/<version>` path: two directories normalizing to the same target (`cinema/1.2-rc1` and `cinema/1.2-dev-a1b2c3` both become `cinema/1.2`), or a target directory that already exists. Both files are reported as **COLLISION** with the target path and are left untouched, including their `version:` value — a partial repair would leave two specs claiming one identity, which is the state a published profile identity must not silently reach. Resolve it by choosing distinct versions by hand and re-running.

A repair that leaves two specs *declaring* the same name and version without sharing a path — repairing `cinema/0.9` to declare `1.2` while `cinema/1.2` exists — is carried out but noted in the report. Nothing is overwritten and both stay addressable by their own directory, and [two specs may legitimately declare one version and differ in content](schema-specs.md#content-hash); `content_hash` is what distinguishes them. The note is there so the duplication is not something you discover later.

#### Report and exit code

One entry per non-conforming spec — its path, the old version, either the new version or the reason no repair was made, and any directory rename — then a summary counting the non-conforming specs, those repaired (`WOULD REPAIR` in a dry run), and those lossy, colliding or needing a manual fix. Conforming specs are not listed. Each entry is labelled:

| Label | Meaning |
|-------|---------|
| `[WOULD REPAIR]` / `[REPAIRED]` | the version was normalized; the two words distinguish a dry run from a write |
| `[LOSSY]` | added to a repair that discarded a patch component |
| `[NEEDS MANUAL FIX]` | no version derivable, or the value is not on a top-level `version:` line and so cannot be replaced without reformatting; file untouched |
| `[COLLISION]` | repair refused to avoid two specs at one name+version |
| `[ERROR]` | the file could not be read, parsed, or written |

| Situation | `--apply` exit code |
|-----------|--------------------|
| Nothing to do, or every non-conforming spec repaired | 0 |
| Specs reported NEEDS MANUAL FIX or LOSSY | 0 — findings, not failures |
| A repair was attempted and did not complete: a refused collision, or a filesystem error | 1 |

A dry run always exits 0; it reports, it does not judge.

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
