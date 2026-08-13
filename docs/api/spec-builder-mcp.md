# Spec Builder MCP Tools

MCP tools for authoring and editing profile specifications from an MCP client
(e.g. Claude Desktop). They expose the same operations as the web spec builder,
backed by the shared [Spec Builder Engine](../architecture/spec-builder.md).

## Session model

The tools operate on a single **active draft** held in the MCP session — one
`SpecBuilder` per session. A typical flow:

1. `spec_create` or `spec_clone` or `spec_import_yaml` — start a draft.
2. `spec_add_entity`, `spec_add_field`, `spec_add_rule`, … — edit it.
3. `spec_validate` — confirm it builds.
4. `spec_compare` — when the draft revises an existing profile, see whether the
   edits are breaking and which version bump they require.
5. `spec_save` — persist it.

There is no draft until one is started; editing tools return an error if called
first. Starting a new draft replaces any unsaved one.

## Linking entities

A profile is a tree, not a set: every entity except the root must be nested under a parent, or datasets built from the profile can never reach it. The link is a field on the parent whose `type` is `list` (many children) or `entity` (exactly one child) and whose `items` names the child entity — adding it auto-creates the parent `identifier` field and the child's back-reference. `spec_set_root_entity` marks the top of the tree. An entity that is not the root and is not named in any other entity's `items` is orphaned; `spec_validate` does not currently flag orphans, so the linking step cannot be skipped and left for validation to catch. The server's MCP instructions state this workflow, so connected agents link entities as they build.

## Addressing

Entities, fields, and rules are addressed **by name**, not list index. Field
names are unique within an entity and rule names are unique within a spec, so an
agent can edit without tracking positions. The single exception is
`spec_move_field`, which reorders by direction (`up` / `down`).

## Tools

### Draft lifecycle

| Tool | Arguments | Description |
|------|-----------|-------------|
| `spec_create` | `name`, `version`, `display_name?`, `description?`, `ontology?` | Start an empty draft. |
| `spec_clone` | `profile`, `version` | Start a draft from a built-in or user spec. |
| `spec_import_yaml` | `yaml_text` | Start a draft from YAML. |
| `spec_status` | — | Summary of the draft: name, version, display name, root entity, each entity's field names, and rule names. |
| `spec_preview_yaml` | — | Current draft serialized to YAML. |
| `spec_validate` | — | Full model build; returns `{"valid": bool, "issues": [...], "warnings": [...]}` (empty issues = valid; warnings never affect `valid`). |
| `spec_compare` | `profile`, `version` | Compare the draft against a released version of `profile`; returns the classified changes and the required version bump. |
| `spec_save` | `name?` | Persist the draft to the user specs directory. |

#### Issues versus warnings

`spec_validate` reports two lists and they are not the same kind of finding.

- **`issues`** are defects: the spec does not build, a reference dangles, the
  `version` is malformed, a rule's `where` names a field that does not exist.
  `valid` is `false` while any issue remains.
- **`warnings`** are advisory: the spec builds and loads, but something in it is
  likely not what the author meant. Warnings never set `valid` to `false` and
  never block `spec_save`.

The current warning is a **weak inferred identifier**: an entity that declares no
`is_identifier` and whose positionally-inferred identifier is an optional,
unconstrained string. Such a field can be absent, duplicated across rows, and
free-form, yet it is what index keys and node IDs are built from — and because
inference always yields *something*, the spec is otherwise reported as valid. The
warning names the entity, the field it would infer, and the fix:

```json
{
  "valid": true,
  "issues": [],
  "warnings": [
    "Assay: no field declares is_identifier, so the identifier is inferred as 'variable_name', an optional free-text field. Mark the intended field with is_identifier: true."
  ]
}
```

The check asks `specs.schema.identifying_field`, the one definition of the rule —
the same one the facade and the version comparator use — so it cannot disagree
with the identifier a dataset actually gets. It stays quiet
when the entity declares `is_identifier`, when the inferred field is `required`,
when it is not a string, when a `pattern`, `enum`, `options` or `unique_within`
already pins its shape or uniqueness, and when the field's own name states that
it is an identifier (`id`, `sample_id`, `locationID`, `database_identifier`, …).
A name that states a *label* (`name`, `title`) is not exempt: an entity's display
label is exactly what the markers exist to keep separate from its identity.

`spec_compare` answers "what do my edits imply?" before the draft is saved. It
loads `profile` at `version` as the *old* side and the active draft as the
*new* side, then returns:

```json
{
  "old": {"profile": "cinema", "version": "1.0", "content_hash": "sha256:1f0a2b3c4d5e"},
  "new": {"version": "1.1", "content_hash": "sha256:9e8d7c6b5a40"},
  "required_bump": "major",
  "declared_bump": "minor",
  "bump_satisfied": false,
  "breaking": [
    {"kind": "field_became_required", "target": "Credit.person",
     "message": "Credit.person became required", "old": false, "new": true}
  ],
  "compatible": []
}
```

`required_bump` is what the content changes demand, `declared_bump` is what the
draft's `version` claims relative to `version`, and `bump_satisfied` is whether
the claim covers the demand. The tool is advisory — it reports, it does not
block `spec_save`. See
[Profile Versioning](schema-specs.md#profile-versioning) for the classification
table and the bump rule.

### Profile metadata

| Tool | Arguments | Description |
|------|-----------|-------------|
| `spec_set_metadata` | `name?`, `version?`, `display_name?`, `description?`, `ontology?` | Update profile-level fields. |
| `spec_set_root_entity` | `entity` | Set the root entity (must already exist). |

### Entities

| Tool | Arguments | Description |
|------|-----------|-------------|
| `spec_add_entity` | `name`, `description?`, `ontology_term?` | Add an entity. |
| `spec_update_entity` | `name`, `description?`, `ontology_term?` | Update an entity's metadata. |
| `spec_rename_entity` | `old_name`, `new_name` | Rename and cascade all references (`items`, `reference`, `parent_ref`, validation rules). |
| `spec_delete_entity` | `name` | Remove an entity; clears `root_entity` if it pointed there. |

### Fields

| Tool | Arguments | Description |
|------|-----------|-------------|
| `spec_add_field` | `entity`, `name`, `field_type`, `required?`, `description?`, `items?`, `ontology_term?`, `reference?`, `parent_ref?`, constraint fields, marker fields | Add a field. A nested field (`field_type` is `list`/`entity` with `items` naming an existing entity) auto-creates the parent `identifier` and the back-reference on the target. |
| `spec_update_field` | `entity`, `field_name`, `field_type?`, `required?`, `description?`, `items?`, `ontology_term?`, `reference?`, `parent_ref?`, constraint fields, marker fields, `clear?` | Update a field in place. Unset arguments keep their current value; supplied constraints merge into the field's existing ones, and `clear` names constraints to remove. |
| `spec_delete_field` | `entity`, `field_name` | Remove a field. |
| `spec_move_field` | `entity`, `field_name`, `direction` | Reorder a field (`up` / `down`). |

`field_type` is one of: `string`, `integer`, `float`, `boolean`, `date`,
`datetime`, `uri`, `ontology_term`, `list`, `entity`. Constraint fields map to
`Constraints`: `pattern`, `min_length`, `max_length`, `minimum`, `maximum`,
`min_items`, `max_items`, `enum`. Marker fields are the remaining `FieldSpec`
attributes: `codename`, `ontologies`, `unique_within`, `dcat`, `owns`,
`is_identifier`, `is_label`, `example`, `options`, `unit`, `label`, `tier`. See
[Specification Language](schema-specs.md) for field semantics and
[Field Markers](schema-specs.md#field-markers) for what each marker means — this
page documents only how to set them, not what they do.

#### Editing constraints

A field's constraints are one `Constraints` object holding all eight values, so
"change the minimum" and "replace the constraints" are different operations and
the tools keep them apart.

`spec_update_field` **merges**. A supplied constraint overwrites that one value
and leaves every other constraint on the field intact, so tightening a range
does not discard an existing `enum` or `pattern`. It creates the constraints
block if the field had none. Because an omitted argument means *unchanged*, it
cannot express removal; that is what `clear` is for — a list of constraint names
to set back to unset.

```
spec_update_field(entity="Study", field_name="rating", minimum=1)
  # enum, maximum and pattern survive untouched

spec_update_field(entity="Study", field_name="rating", clear=["maximum"])
  # removes maximum only

spec_update_field(entity="Study", field_name="rating", minimum=0, clear=["enum"])
  # set and clear in one call
```

Naming the same constraint both as an argument and in `clear` is rejected: the
two say opposite things, and guessing which wins would hide the mistake. An
unknown name in `clear` is rejected with the list of valid names.

Clearing the last remaining constraint drops the whole `constraints` block
rather than leaving an all-unset one, so the field serializes without a
`constraints:` key and the spec's `content_hash` matches an otherwise identical
spec whose field never carried constraints.

#### Declaring identity and labels

An entity's identifier and display label are otherwise inferred from field
*position* — the identifier is the first non-reference field, the label is the
first field. `is_identifier` and `is_label` override that, so field order stays a
presentation decision instead of silently deciding entity identity. The markers
are read whatever the spec's `spec_version` is.

```
spec_add_field(entity="Assay", name="input", field_type="string")
spec_add_field(entity="Assay", name="file_name", field_type="string",
               required=True, is_identifier=True, is_label=True)
  # identifier is file_name, not the positionally-first `input`
```

Marking a field already in the draft is one call:

```
spec_update_field(entity="Assay", field_name="file_name", is_identifier=True)
```

At most one field per entity may set each marker. A second one is reported by
`spec_validate` as an issue (it is what makes the spec unloadable), so mark the
new field and unmark the old one in either order and validate before saving.

#### Setting and unsetting markers

Every marker follows the same rule as the rest of `spec_update_field`: an
**omitted** argument leaves the current value alone. Unlike a constraint, a
marker has an expressible empty value, so removal does not need `clear` —
passing `false` for a boolean marker, `""` for a text marker, or `[]` for a list
marker unsets it. An unset marker is absent from the YAML rather than written as
`false` or `""`, so a spec's `content_hash` does not depend on whether a marker
was ever toggled.

```
spec_update_field(entity="Assay", field_name="file_name", unit="")
  # removes the unit; every other marker on the field is untouched
```

A list-valued marker (`options`, `ontologies`) is **replaced**, not merged. This
mirrors constraints, where the merge granularity is the named constraint and the
list-valued `enum` is likewise swapped whole: `options` is one controlled
vocabulary, not eight independent values, so appending a term means resending the
list.

`tier` accepts only `required`, `recommended` or `optional`; any other value is
rejected before the draft is touched. `example` is set as a string here — richer
example types (numbers, booleans, lists) remain available to hand-authored YAML
through `spec_import_yaml`.

### Validation rules

| Tool | Arguments | Description |
|------|-----------|-------------|
| `spec_add_rule` | `name`, rule fields | Add a validation rule. |
| `spec_update_rule` | `rule_name`, rule fields | Update a rule. |
| `spec_delete_rule` | `rule_name` | Remove a rule. |

Both tools take every attribute of `ValidationRuleSpec`: `type`, `description`,
`message`, `applies_to`, `field`, `condition`, `pattern`, `minimum`, `maximum`,
`enum`, `reference`, `unique_within`, `min_items`, `max_items`, `lat_field`,
`lon_field`, `start_field`, `end_field`, `where`, `when`, `require`. A test gates that list against
the model, so a key added to the rule format is unauthorable over MCP only until
that test is made to pass — half of them were missing before #211, which is why
an agent could declare a cardinality rule's type but not its bounds.

`where` is a predicate selecting which items a cardinality rule counts, passed as
a mapping:

```python
spec_add_rule(
    name="exactly_one_display_column",
    type="cardinality",
    applies_to="SampleType",
    field="attributes",
    min_items=1,
    max_items=1,
    where={"field": "is_display_column", "op": "==", "value": True},
)
```

Groups are `{"all": [...]}`, `{"any": [...]}` and `{"not": {...}}`; the
operators are `==`, `!=`, `in`, `not_in`, `>`, `>=`, `<`, `<=`, `is_set` and
`is_not_set`. `when` is the same shape and pairs with `require` to make a
requirement depend on a value. A predicate naming a field the counted entity does not declare is
reported by `spec_validate` as an issue, not a warning: the rule carrying it
would never fire. See [Rule Predicates](schema-specs.md#rule-predicates).

## Return values and errors

Every tool returns a JSON string. Success returns the affected state (e.g. a
status summary or the updated entity). Failures return `{"error": "<message>"}`
— for example editing before a draft exists, naming an entity that does not
exist, or a name that collides with a built-in profile on save. Errors do not
raise; the client reads them from the result.

## Example session

```
spec_create(name="my-trait", version="0.1", display_name="My Trait Profile")
spec_add_entity(name="Investigation", description="Top-level container")
spec_set_root_entity(entity="Investigation")
spec_add_entity(name="Study")
spec_add_field(entity="Investigation", name="studies", type="list", items="Study")
  # auto-creates Investigation.identifier and Study.investigation_id back-reference
spec_add_field(entity="Study", name="title", type="string", required=True)
spec_validate()            # -> {"valid": true, "issues": []}
spec_save()                # -> {"status": "saved", "path": "…/profile.yaml"}
```
