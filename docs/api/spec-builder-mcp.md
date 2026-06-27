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
4. `spec_save` — persist it.

There is no draft until one is started; editing tools return an error if called
first. Starting a new draft replaces any unsaved one.

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
| `spec_status` | — | Summary of the draft: name, version, root entity, entity and field counts, whether it has been saved. |
| `spec_preview_yaml` | — | Current draft serialized to YAML. |
| `spec_validate` | — | Full model build; returns issues (empty list = valid). |
| `spec_save` | `name?` | Persist the draft to the user specs directory. |

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
| `spec_add_field` | `entity`, `name`, `type`, `required?`, `description?`, `items?`, `ontology_term?`, `reference?`, `parent_ref?`, constraint fields | Add a field. A nested field (`type` is `list`/`entity` with `items` naming an existing entity) auto-creates the parent `identifier` and the back-reference on the target. |
| `spec_update_field` | `entity`, `field_name`, editable fields | Update a field in place. |
| `spec_delete_field` | `entity`, `field_name` | Remove a field. |
| `spec_move_field` | `entity`, `field_name`, `direction` | Reorder a field (`up` / `down`). |

`type` is one of: `string`, `integer`, `float`, `boolean`, `date`, `datetime`,
`uri`, `ontology_term`, `list`, `entity`. Constraint fields map to
`Constraints`: `pattern`, `min_length`, `max_length`, `minimum`, `maximum`,
`min_items`, `max_items`, `enum`. See
[Specification Language](schema-specs.md) for field semantics.

### Validation rules

| Tool | Arguments | Description |
|------|-----------|-------------|
| `spec_add_rule` | `name`, rule fields | Add a validation rule. |
| `spec_update_rule` | `rule_name`, rule fields | Update a rule. |
| `spec_delete_rule` | `rule_name` | Remove a rule. |

Rule fields follow `ValidationRuleSpec`: `type`, `message`, `applies_to`,
`field`, `condition`, `pattern`, `minimum`, `maximum`, `enum`, `reference`,
`min_items`, `max_items`, `lat_field`, `lon_field`, `start_field`, `end_field`.

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
spec_validate()            # -> []  (builds cleanly)
spec_save()                # -> persisted to the user specs directory
```
