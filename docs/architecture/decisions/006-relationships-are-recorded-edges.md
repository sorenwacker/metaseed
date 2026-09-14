# ADR 006: Relationships are recorded edges, not inferred from types

Date: 260914

## Status

Accepted

## Context

metaseed stores a dataset as a tree: every entity has at most one parent, and a parent's nested field (`list` or `entity` of an entity type) names its children by identifier. ADR 005 put the decisions of that invariant in `metaseed.facade.linking`. One of those decisions — `target_reference_field`, "the first nested field whose type matches the child's type" — is an inference, and it is wrong whenever a parent holds one child type in more than one field.

A DCAT-AP profile (Health-RI core v2) exposed this and two related defects:

1. **The edge label is not recorded.** A Catalog has `creator` (list of Agent) and `publisher` (one Agent). Nothing stores which field a child belongs to, so every consumer re-infers it from the child's type:
   - `DocumentLoader` drops the field when it splits an embedded child from its parent, so a loaded example has every relation field empty (reproduced with the shipped ENA example as well).
   - `ui/helpers/entity_helpers.extract_nested_from_tree` groups children into tables by type, so the publisher is shown as a second creator and the Publisher table is empty.
   - `repositories/helpers.update_parent_reference`, the MCP `create_entity` tool, `api/validation.py`, `pride/export.py` and the store's unlink path all call `target_reference_field`.
   - metaseed-hub's `ui/routes/table.py` selects children with `c.entity_type == nested_type`, a further copy.
   - The serialized dataset records `_parent_unique_id` / `_parent_id` but no field.
2. **Identifier lookups are global.** `EntityStore._index` maps an identifier *value* to a node regardless of entity type. A QualityCertificate whose first field (`target`) holds the dataset's IRI replaced the Dataset in the index, so on reload the Dataset's thirteen descendants were attached under the certificate, disconnected from the root, and a subsequent save dropped them.
3. **Shared entities must be copied.** DCAT is a graph: one organisation publishes a catalogue and several of its datasets; a Distribution names the DataService that serves it. The tree allows one parent per entity, so the Health-RI example holds eight Agent records where the catalogue references a few organisations. The spec format already distinguishes containment (`owns: true`) from lookup (an unmarked relationship), but only `DocumentLoader` honours `owns`; forms, tables, the store and the MCP tools treat every relationship field as containment.

Each defect was fixed once somewhere in the past and re-appeared elsewhere, because the fact that would prevent it — which field, which type, owned or referenced — is not stored and has to be recomputed.

## Decision

A dataset is a set of entities connected by **edges**. An edge is recorded when it is created and read by every consumer; no component infers an edge from entity types.

- **Containment edge** — `(parent, field, child)` for a field marked `owns: true`. A child has at most one containment edge. The containment edges form the tree the UI navigates and the exporters walk.
  - `EntityNode` and `EntityData` carry `parent_field` beside `parent_id`.
  - `linking.link_child(parent, child, field)` sets both and writes the child's reference into that field (append for `list`, claim for `entity`, per ADR 005's shape rule).
  - Every creation path passes the field: `DocumentLoader` (the field the child was embedded in), the UI add-child routes (the table's field), the MCP `create_entity` tool (a `parent_field` argument), repositories, the Excel import.
  - When a caller does not name a field and the parent has exactly one candidate field for the child's type, that field is used. With more than one candidate the call is rejected and the error lists the candidates. `target_reference_field`'s silent first match is removed.
- **Reference edge** — `(entity, field, target)` for a relationship field not marked `owns`, and for `reference:` fields. The field holds the target's identifier; the target may be anywhere in the dataset and may be referenced from any number of fields. Deleting a referenced entity is reported, not cascaded.
- **Lookups are scoped by type.** The store resolves an identifier as `(entity_type, value)`. A reference field names its target type (`items:` or `reference:`), so resolution never crosses types.
- **Profiles without `owns` markers** keep their current meaning — every relationship field is containment — so shipped profiles and existing datasets load unchanged.

### Serialization

A serialized entity records `_parent_field` beside `_parent_unique_id`. Reading a file without `_parent_field` resolves the field from the parent's own field values (the field whose value names the child); a child no field names falls back to the single candidate field, and otherwise is loaded under the parent with a warning naming the candidates. `metaseed migrate-datasets` writes `_parent_field` into existing files.

### UI

- A containment field is rendered once, as its child table, by the one partial that draws such a table. It appears in the field's own place when the field is listed among the required or optional fields, and under Related Entities otherwise. It no longer also appears as a "(1 item)" / "(not set)" button among the fields: a required containment field was listed twice, as an unlabelled button near the top and as its table far below.
- A reference field is rendered as a picker of existing entities of the target type, with an action to create one.
- "Add child entity" names the field ("+ publisher (Agent)"), not only the type.

## Enforcement

- `tests/test_tree_linking_is_owned_once.py` gains a gate: `target_reference_field` (or any selection of a parent field by child type) may not appear outside `facade/linking.py`, in metaseed and in metaseed-hub.
- A profile fixture with two fields of one child type (`creator`, `publisher`) and one owned and one referenced relationship runs through: document load, UI table grouping, MCP create, repository create, save and reload round trip, export. Each asserts the child is in the field it was created in.
- A store test: two entities of different types with the same identifier value both resolve to themselves.
- Each test is shown to fail on `main` before the change.

## Consequences

- The field a child belongs to cannot be lost by one component and guessed differently by another, because no component guesses.
- DCAT-style profiles can reference shared Agents and Kinds instead of copying them; the Health-RI profile is reworked to own datasets, services, series and distributions, and to reference agents and contact points.
- MCP `create_entity` callers must name `parent_field` when a parent has several candidate fields; today such calls silently pick the first field.
- metaseed-hub changes in the same release: `ui/routes/table.py` and `ui/helpers/tree.py` read `parent_field`, and the hub's stored dataset payloads are migrated.
- The work lands as separate PRs in this order: (1) type-scoped lookups; (2) recorded containment field through store, loader, repositories, MCP, serialization and migration; (3) UI rendering of containment and reference fields; (4) reference edges for non-owned relationship fields; (5) Health-RI profile rework. Each PR is usable on its own.
