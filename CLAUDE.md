# Metaseed Project Context

## Overview

Metaseed is a schema-driven metadata management system that creates, edits, and validates structured metadata from YAML specifications. It supports scientific metadata standards including MIAPPE, ISA, DiSSCo, and Darwin Core.

## Key Files to Read First

### Specification System
- `src/metaseed/specs/schema.py` - Pydantic definitions for spec structure (ProfileSpec, EntityDefSpec, FieldSpec, etc.)
- `src/metaseed/specs/loader.py` - YAML loading and caching

### Model Generation
- `src/metaseed/models/factory.py` - Dynamic Pydantic model generation from specs
- `src/metaseed/models/registry.py` - Model caching and retrieval

### Example Specifications
- `src/metaseed/specs/miappe/1.2/profile.yaml` - MIAPPE profile
- `src/metaseed/specs/dissco/0.4/profile.yaml` - DiSSCo profile
- `src/metaseed/specs/isa/1.0/profile.yaml` - ISA profile
- `src/metaseed/specs/darwin-core/1.0/profile.yaml` - Darwin Core profile

### Documentation
- `docs/api/schema-specs.md` - Complete spec format reference
- `docs/architecture/overview.md` - Architecture overview

## Specification Structure

All specs live under `src/metaseed/specs/<profile-name>/<version>/profile.yaml`.

A profile.yaml contains:
- `version`, `name`, `display_name`, `description`
- `root_entity` - the top-level entity
- `ontology` - ontology prefix
- `entities` - dictionary of entity definitions
- `validation_rules` - cross-entity validation

Each entity has:
- `ontology_term`, `description`
- `fields` - list of field definitions
- `example` (optional)

Each field has:
- `name`, `codename`, `type`, `required`, `description`
- `ontology_term`, `constraints`, `items` (for lists/entities)

Field types: `string`, `integer`, `float`, `boolean`, `date`, `datetime`, `uri`, `ontology_term`, `list`, `entity`

## Tech Stack

- Python 3.11+, Pydantic 2.0+, FastAPI, Typer, HTMX
- uv for dependency management
- pytest for testing
- MkDocs for documentation

## Development Cycle

Conventions that keep a green CI meaning "correct". Each is grounded in a defect
that a passing suite failed to catch (see issue #139 and its follow-ups).

### Tests must be able to fail

- Before committing a test, confirm it goes red against the unfixed code. A test
  that passes on broken output is worse than none: a conformance test once
  certified a header-only MetaboLights export as valid, and an importer produced
  zero samples under a passing test.
- For adapters and validators, assert on content, not on existence or counts.
- Do not record a bug or review finding without a runnable reproduction. An
  unreproducible finding is a hypothesis.

### Gates, not cleanup

- Drift between two things that must agree is caught by a test, not a periodic
  sweep. Existing gates in `tests/test_docs/`: every entity and field named in a
  profile page's mermaid diagram must exist in the loaded `ProfileSpec`, every
  fenced example must execute, and every `metaseed` import shown in the docs must
  resolve. Keep these green rather than editing around them.
- Proposed, not yet implemented: a per-profile
  create -> serialize -> load -> validate round-trip test (would have caught the
  #141 cardinality bug and the reload-fidelity gap); a public-API surface
  snapshot guarding the metaseed-hub contract (#68); an ERD relationship-edge
  check (a page edge must name a real nested field whose `items` is the target).

### Local must match CI

- `make test` and CI must exclude the same markers. CI runs
  `-m "not selenium and not network"`; keep the Makefile in step so the local
  default is neither slower nor less hermetic than CI.
- `network`-marked tests hit live third-party APIs (EBI/MetaboLights) and are
  excluded from CI, so they give no regression protection until recorded as
  fixtures. Do not rely on them as the only cover for an adapter.
- Formatting is gated in CI (`ruff format --check`). The pre-commit `ruff` pin
  must match the `ruff` version resolved in `uv.lock`; drift produces repo-wide
  reformat commits.

### Commits and PRs

- Atomic commits: never mix a formatting reflow with substantive content. A
  `style:` commit that also adds code or docs hides that content from review.
- Keep PRs small and current; rebase onto `main` rather than letting a branch
  drift behind it.

### No real personal data in examples or fixtures

- Never commit real sensitive data to the repository. Example specs, fixtures,
  and documentation must use synthetic identities only: fictional person names,
  `@example.org` emails, obviously-fake ORCIDs, and invented institutions,
  addresses, coordinates, and place names.
- This applies even when the source is a public database (PRIDE, MetaboLights,
  ENA, etc.): importing a real record does not license redistributing the
  submitters' names, emails, or affiliations in the test suite or the package.
  De-identify on the way in.
- Real technical references stay real: ontology/database URLs and accessions
  (EFO, CHEBI, the EBI API endpoints the code actually calls) are not personal
  data and must remain correct.
- The source distribution ships only `src/metaseed` plus build metadata
  (`[tool.hatch.build.targets.sdist]` `only-include`); `tests/` must never be
  packaged, so fixtures never reach PyPI.
