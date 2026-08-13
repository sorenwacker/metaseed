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
| Output | `to_yaml()`, `validate()`, `warnings()` |

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

The same reading extends to the field markers (`owns`, `is_identifier`,
`is_label`, `example`, `options`, `unit`, `label`, `tier`, plus `codename`,
`ontologies`, `unique_within` and `dcat`). Each is one whole attribute, so
`update_field` assigns it whole and no third convention is needed: the scalar
markers are indistinguishable from a partial update, and the two list-valued ones
(`options`, `ontologies`) are single values — one controlled vocabulary, one
ontology list — not containers of independently addressable named values the way
`Constraints` is. `Constraints` earned `update_field_constraints` because one
attribute holds eight *named* values; a list has no names to merge on, which is
why `enum` is already swapped whole inside that merge. `options` and `ontologies`
are replaced for the same reason.

Markers also need no `clear` counterpart. `clear` exists because an omitted
numeric constraint cannot express "remove"; a marker can, because its empty value
is representable — `False`, `""`, `[]`. `specs.builder.normalize_markers` maps
those onto `None`, matching `FieldForm.apply_to`, so an unset marker is absent from the
serialized spec rather than written as `owns: false` and the `content_hash` does
not record whether a marker was ever toggled.

`FIELD_MARKER_NAMES` is derived from `FieldSpec.model_fields` by subtracting the
core authoring attributes the field tools already took as named arguments
(`name`, `type`, `required`, `description`, `items`, `ontology_term`,
`reference`, `parent_ref`, `constraints`). It is exported for the same reason as
`CONSTRAINT_NAMES`: an adapter (the MCP tools here, the metaseed-hub spec tools
downstream) mirrors the set instead of hardcoding it, and a new `FieldSpec`
attribute becomes settable without a second edit. A test asserts every name in the
tuple is a parameter of both field tools, so adding an attribute to the schema
fails the suite until it is either exposed or deliberately added to the core set.

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

`validate()` reports a container field that names no element type: a `list` or `entity` field with no `items`. The model build cannot catch this — `list` maps to `list[Any]` and `entity` to `Any` regardless of `items` — so such a field builds cleanly while accepting anything and never resolving as a nested entity. An `items` value naming a primitive (`string`, `integer`, …, see `specs.schema.PRIMITIVE_TYPES`) is a valid list element type and is not an issue; only an absent or empty `items` is.

`validate()` returns a list of issues; an empty list means the spec builds
cleanly.

### Advisories: `warnings()`

`warnings()` reports findings that are not defects. The spec builds, loads and
validates datasets; something in it is merely unlikely to be what the author
meant. It is a second method rather than extra entries in `validate()` for two
reasons. A non-empty `validate()` means "this spec is broken" to every caller —
the MCP `spec_validate` tool derives `valid` from it, and metaseed-hub's spec
tools surface it as `problems` at a dozen call sites — so an advisory placed
there would flip valid specs to invalid. And the documented `list[str]` return
shape stays exactly as it was, so no caller has to change to keep working.

The one advisory today is a **weak inferred identifier**. `EntityHelper` resolves
an entity's identifier from a declared `is_identifier` marker, falling back to the
first non-reference field. The fallback always yields *something*, so an entity
identified by an optional, free-form column validates silently while its index
keys and node IDs are built on a value that may be absent or repeated. The check
duplicates that inference rule (the helper needs a built `EntitySpec`, which a
draft mid-edit may not produce) so the advisory cannot name a different field
than the one a dataset is actually keyed by.

A field is reported only when nothing in the spec says its value will be present
(`required`), distinguishing (`unique_within`) or shaped (`pattern`, `enum`,
`options`), it is a `string`, and its own name does not state that it is an
identifier — `id`, `sample_id`, `locationID`, `database_identifier` are taken at
their word. `name` and `title` are not exempt: they state a display *label*, and
keeping labels distinct from identity is the reason the markers exist.

The name check is a heuristic, and it is confined to suppressing advice. It never
resolves identity and never changes what a dataset is keyed by; at worst it
withholds a suggestion. That is a different risk class from the heuristics the
markers replaced, which silently picked the wrong field.

The advisory fired five times across the ten shipped profiles (#212), and the
five were not one problem:

- `isa` 1.0 `Process.name`, `miappe-htp` 1.0 `Location.name` and
  `ObservationLevelHierarchy.name` are entities whose identifier *is* that field
  — it was simply never declared. They now declare it. Nothing about them is
  keyed differently: the marker names the field inference already resolved to,
  which the [comparator](../api/schema-specs.md#comparing-versions) classifies
  compatible, so no version was bumped to record it. That reclassification was
  the substance of the fix; before it, saying out loud what the format already
  did counted as a breaking change.
- `miappe-htp` 1.0 `SpatialDistribution` has no identifier. It is a value object
  nested one-to-one in an ObservationUnit — a description and three coordinates
  — and marking any of them would state an identity the entity does not have.
  The advisory is accurate and stays.
- `pride` 1.0 `Publication` is identified by its `doi`, not by the `title`
  inference picks. Moving it is a real change to what datasets are keyed by, so
  it belongs in a MAJOR version rather than in a patch.

A test pins the expected set per profile, so a profile edit cannot introduce a
new weak identifier unnoticed.

## The rule editor

Validation rules are edited by name, one form per rule, with the fields shown
per rule type. Two of those fields are predicates (`where` on a cardinality or
uniqueness rule, `when` on a conditional one), and they are edited as repeated
rows of field / operator / value with an all-or-any toggle, assembled into the
structured predicate server-side.

Rows rather than a text box, because the field can then be offered from the
fields the counted entity actually declares — which puts the load-time "unknown
field" error out of the editor's reach instead of moving it to after the save.
Values are read as YAML, which is how the same value would be written in the
profile: `true` is a boolean, `3` a number, `[a, b]` a list.

A flat group is what rows can express. A predicate loaded from YAML that nests
deeper is shown read-only as its one-line `render_predicate()` spelling and
posted back untouched: the editor not being able to show something is not a
reason to destroy it.

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
