# Spec Builder Engine

## Overview

The spec builder authors and edits profile specifications (`profile.yaml`). The
authoring logic lives in a single domain module, `src/metaseed/specs/builder.py`,
exposed through two interfaces that share it:

- the web UI (`src/metaseed/ui/spec_builder/`), and
- the MCP server (`src/metaseed/agent/mcp/tools/spec_builder.py`).

**Key principle**: the engine has no UI or MCP dependencies. Both interfaces are
thin adapters over `SpecBuilder`. This mirrors the extraction agent's separation
(see [Metadata Extraction Agent](metadata-agent.md)) and ensures the two
interfaces cannot drift apart, because they execute the same code.

## Motivation

Before this module, two pieces of authoring logic were embedded in the UI route
handlers:

- the entity-rename cascade (`_update_entity_references` in
  `ui/spec_builder/routes_entities.py`), which rewrites `field.items`,
  `field.reference`, `field.parent_ref`, and validation-rule `applies_to` /
  `reference` when an entity is renamed; and
- auto back-reference creation (`_auto_create_back_reference` in
  `ui/spec_builder/routes_fields.py`), which inserts an `identifier` field on the
  parent and a back-reference field on the target when a nested field is added.

Exposing spec authoring over MCP without extracting this logic would have
duplicated it, creating the same drift risk as the historical reference-resolution
defects (findings H2 and M19 in `docs/REVIEW.md`). Extraction makes one
implementation authoritative.

## Architecture

```
┌──────────────────────┐     ┌──────────────────────────────┐
│   UI spec_builder    │     │   MCP tools/spec_builder.py  │
│   routes_*.py        │     │   spec_create, spec_add_*…   │
└──────────┬───────────┘     └───────────────┬──────────────┘
           │                                 │
           └───────────────┬─────────────────┘
                           │
              ┌────────────┴─────────────┐
              │  specs/builder.py        │
              │  SpecBuilder             │
              └────────────┬─────────────┘
                           │
        ┌──────────────────┼───────────────────┐
        │                  │                    │
┌───────┴──────┐  ┌────────┴────────┐  ┌────────┴────────┐
│ specs/schema │  │ specs/loader    │  │ specs/          │
│ ProfileSpec… │  │ (clone source)  │  │ persistence.py  │
└──────────────┘  └─────────────────┘  └─────────────────┘
```

## SpecBuilder

`SpecBuilder` wraps a single mutable `ProfileSpec` and is the only place spec
mutations are defined.

### Construction

| Constructor | Behavior |
|-------------|----------|
| `SpecBuilder.empty(name, version, *, display_name=None, description="", ontology=None)` | New spec with no entities. |
| `SpecBuilder.from_template(profile, version)` | Deep-copy a built-in or user spec loaded via `SpecLoader`; the version is suffixed to mark it as a derivative. |
| `SpecBuilder.from_yaml(text)` | Parse YAML and validate with `ProfileSpec.model_validate`. |
| `SpecBuilder.from_spec(spec)` | Wrap an existing `ProfileSpec` (used by the UI to adopt `SpecBuilderState.spec`). |

`builder.spec` returns the underlying `ProfileSpec`.

### Operations

| Group | Methods |
|-------|---------|
| Profile | `set_metadata(**fields)`, `set_root_entity(name)` |
| Entities | `add_entity(name, *, description="", ontology_term=None)`, `update_entity(name, **fields)`, `rename_entity(old, new)`, `delete_entity(name)` |
| Fields | `add_field(entity, name, type, **fields)`, `update_field(entity, field_name, **fields)`, `delete_field(entity, field_name)`, `move_field(entity, field_name, direction)` |
| Rules | `add_rule(name, **fields)`, `update_rule(rule_name, **fields)`, `delete_rule(rule_name)` |
| Output | `to_yaml()`, `validate()` |

`rename_entity` performs the reference cascade. `add_field` performs auto
back-reference creation when the new field is nested (`type` is `list` or
`entity` and `items` names an existing entity). Both behaviors are identical to
the pre-extraction UI behavior.

Index bookkeeping (which field is being edited) is a UI concern and stays in
`SpecBuilderState`; `SpecBuilder` addresses fields and rules by name.

### Validation

`validate()` performs a full model build, not only structural checks. It
constructs `ProfileFacade(spec.name, spec.version, spec=self.spec)`, which runs
every entity through `models.factory.create_model_from_spec`. This exercises the
same code path a real load uses, so type, constraint, and reference errors
surface during authoring. The facade accepts a pre-loaded `spec`
(`facade/core.py`), so validation runs in memory without writing a file.

`validate()` returns a list of issues; an empty list means the spec builds
cleanly.

## Persistence

User-created specs are written under the platform data directory
(`src/metaseed/specs/persistence.py`), separate from the built-in specs shipped
in `src/metaseed/specs/<profile>/<version>/`. Saving refuses names that collide
with a built-in profile. Persistence is independent of both UI and MCP so either
interface can save a draft.

## Interface adapters

- **UI**: `routes_*.py` hold an in-progress `ProfileSpec` in
  `SpecBuilderState.spec` and call `SpecBuilder(state.spec).<op>()` per request,
  then track edit indices and unsaved-changes flags for rendering.
- **MCP**: one `SpecBuilder` draft lives in the MCP session. See
  [Spec Builder MCP Tools](../api/spec-builder-mcp.md) for the tool reference.
