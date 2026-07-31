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
duplicated it, creating the same drift risk as historical reference-resolution
defects. Extraction makes one implementation authoritative.

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
| `SpecBuilder.from_template(profile, version)` | Deep-copy a built-in or user spec loaded via `SpecLoader`, keeping its `version`. The draft is a derivative of that version; the author sets the new profile name and version with `set_metadata` before saving. Profile versions are `MAJOR.MINOR` ([Profile Versioning](../api/schema-specs.md#profile-versioning)), so a draft cannot carry a marker suffix and stay loadable. |
| `SpecBuilder.from_yaml(text)` | Parse YAML and validate with `ProfileSpec.model_validate`. |
| `SpecBuilder.from_spec(spec)` | Wrap an existing `ProfileSpec` (used by the UI to adopt `SpecBuilderState.spec`). |

`builder.spec` returns the underlying `ProfileSpec`.

### Operations

| Group | Methods |
|-------|---------|
| Profile | `set_metadata(**fields)`, `set_root_entity(name)` |
| Entities | `add_entity(name, *, description="", ontology_term=None)`, `update_entity(name, **fields)`, `rename_entity(old, new)`, `delete_entity(name)` |
| Fields | `add_field(entity, name, type, **fields)`, `update_field(entity, field_name, **fields)`, `update_field_constraints(entity, field_name, *, clear=(), **values)`, `delete_field(entity, field_name)`, `move_field(entity, field_name, direction)` |
| Rules | `add_rule(name, **fields)`, `update_rule(rule_name, **fields)`, `delete_rule(rule_name)` |
| Output | `to_yaml()`, `validate()` |

`rename_entity` performs the reference cascade. `add_field` performs auto
back-reference creation when the new field is nested (`type` is `list` or
`entity` and `items` names an existing entity). Both behaviors are identical to
the pre-extraction UI behavior.

Index bookkeeping (which field is being edited) is a UI concern and stays in
`SpecBuilderState`; `SpecBuilder` addresses fields and rules by name.

### Update semantics: whole attributes versus constraints

The `update_*` methods assign each supplied attribute onto the target object.
Per attribute this is a replacement, which for a scalar (`required`,
`description`) is indistinguishable from a partial update. It is not
indistinguishable for `FieldSpec.constraints`, because one attribute holds eight
values: `update_field(entity, name, constraints=Constraints(minimum=1))` sets the
field's constraints *to that object*, discarding any `enum`, `pattern` or
`maximum` it previously carried.

`update_field_constraints` is the partial-update path, kept a separate method
rather than a flag on `update_field` for two reasons. The two methods take
different key spaces — `update_field(**attrs)` takes `FieldSpec` attribute names,
`update_field_constraints(**values)` takes `Constraints` field names, and
`pattern`, `minimum` and `maximum` exist in neither dictionary as the same thing
— so merging them into one signature would make `pattern=` ambiguous. And a
caller that genuinely holds a complete constraint set (the web field editor,
below) should not have to opt out of merging.

It merges the supplied values over the field's current constraints, creates the
object when the field has none, and takes `clear` — an iterable of constraint
names to unset, since an omitted keyword cannot mean "remove". A name that is
neither in `Constraints` nor valid for `clear` raises `ValueError` listing the
valid names; a name given both as a value and in `clear` raises rather than
resolving an order of precedence.

When the merge leaves every constraint unset, `constraints` is set to `None`
rather than an all-`None` object. Both would validate, but they are not
interchangeable downstream: `canonical_json` dumps with `exclude_none=True`, so
an empty `Constraints` survives as `"constraints":{}` while `None` drops out
entirely, and the same spec would otherwise carry two different
`content_hash` values depending on its edit history. `SpecBuilder.to_yaml` uses
the same `exclude_none=True` dump, so the distinction is equally visible in the
saved file.

### Validation

`validate()` performs a full model build, not only structural checks. It
constructs `ProfileFacade(spec.name, spec.version, spec=self.spec)`, which runs
every entity through `models.factory.create_model_from_spec`. This exercises the
same code path a real load uses, so type, constraint, and reference errors
surface during authoring. The facade accepts a pre-loaded `spec`
(`facade/core.py`), so validation runs in memory without writing a file.

`validate()` also reports a `version` that is not `MAJOR.MINOR`. `ProfileSpec`
rejects such a value when a spec is *loaded*, but attribute assignment on an
existing draft is not re-validated, so `set_metadata(version=…)` can leave a
draft that would not load back. Reporting it as an issue keeps the draft
editable and still catches the problem before `save_spec` writes the file
(which refuses it outright). See
[Profile Versioning](../api/schema-specs.md#profile-versioning).

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
  then track edit indices and unsaved-changes flags for rendering. The field
  editor posts every constraint input on every save, so it goes through
  `FieldForm.apply_to` and replaces the constraints wholesale — an omitted value
  there means the user emptied the box, not that the value is unchanged. This is
  the one place where whole-object replacement is the correct reading of the
  input.
- **MCP**: one `SpecBuilder` draft lives in the MCP session. See
  [Spec Builder MCP Tools](../api/spec-builder-mcp.md) for the tool reference.
