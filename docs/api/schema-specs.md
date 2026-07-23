# Specification Language

Metaseed uses a YAML-based specification language to define metadata schemas. Specifications describe entities (data structures), their fields, relationships, and validation rules.

## Overview

A specification (spec) defines a complete metadata standard. Metaseed includes built-in specs for MIAPPE, ISA, DiSSCo, Darwin Core, and others. You can create custom specs using the Spec Builder UI or by writing YAML directly.

```yaml
spec_version: "0.2"
name: my-profile
version: "1.0"
display_name: My Profile
description: Custom metadata schema for my project
root_entity: Project
ontology: myonto

ontologies:
  OBI:
    name: Ontology for Biomedical Investigations
    uri: http://purl.obolibrary.org/obo/obi.owl
    ols_id: obi

entities:
  Project:
    description: Top-level container
    fields:
      - name: identifier
        type: string
        required: true
      - name: title
        type: string
      - name: studies
        type: list
        items: Study

  Study:
    description: A research study
    fields:
      - name: identifier
        type: string
        required: true
      - name: project_id
        type: string
        parent_ref: Project.identifier

validation_rules:
  - name: identifier_format
    applies_to: all
    field: identifier
    pattern: "^[A-Za-z0-9_-]+$"
```

## Profile Structure

| Field | Required | Description |
|-------|----------|-------------|
| `spec_version` | no | Specification format version (default: "0.1") |
| `name` | yes | Profile identifier (lowercase, hyphens) |
| `version` | yes | Version string (e.g., "1.0", "2.1") |
| `display_name` | no | Human-friendly name for UI |
| `description` | no | Profile description |
| `ontology` | no | Base ontology prefix (e.g., PPEO, OBI) |
| `ontologies` | no | Dictionary of ontology definitions (spec_version 0.2+) |
| `root_entity` | no | Primary entity type (default: "Investigation") |
| `entities` | yes | Dictionary of entity definitions |
| `validation_rules` | no | Cross-entity validation rules |

## Specification Format Versions

The `spec_version` field indicates which version of the specification language format is used. This is distinct from the profile's own `version` field.

| spec_version | Description |
|--------------|-------------|
| `0.1` | Initial format. Implicit default for existing specs. |
| `0.2` | Adds `ontologies` section for structured ontology definitions. |
| `0.3` | Adds explicit `type` and `message` fields to validation rules, plus `lat_field`, `lon_field`, `start_field`, `end_field` for explicit field configuration. |
| `0.4` | Adds `ontologies` field to FieldSpec for scoping `ontology_term` type fields to specific OLS ontologies. |
| `0.5` | Adds `dcat` field to FieldSpec for mapping a root entity's fields onto DCAT/DCAT-AP properties (see DCAT Mapping). |

Existing specs without `spec_version` are automatically treated as version `0.1`.

## Ontologies Section

The `ontologies` section (spec_version 0.2+) defines ontologies used in the profile. Each entry maps an ontology prefix to its definition.

```yaml
ontologies:
  OBI:
    name: Ontology for Biomedical Investigations
    uri: http://purl.obolibrary.org/obo/obi.owl
    ols_id: obi
  ENVO:
    name: Environment Ontology
    uri: http://purl.obolibrary.org/obo/envo.owl
    ols_id: envo
  PO:
    name: Plant Ontology
    uri: http://purl.obolibrary.org/obo/po.owl
    ols_id: po
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Human-readable ontology name |
| `uri` | no | Namespace URI for the ontology |
| `ols_id` | no | OLS4 identifier for lookups via the ontology tools |

The `ols_id` enables integration with the OLS4 ontology lookup tools. When defined, users can search for terms within specific ontologies referenced by the profile.

## Entities

Entities represent distinct data structures in your schema. Each entity has a name (PascalCase) and contains fields.

```yaml
entities:
  Sample:
    ontology_term: OBI:0000747
    description: A physical specimen collected for analysis
    fields:
      - name: identifier
        type: string
        required: true
      - name: organism
        type: string
      - name: collection_date
        type: date
    example:
      identifier: "SAMPLE001"
      organism: "Arabidopsis thaliana"
      collection_date: "2024-03-15"
```

| Field | Required | Description |
|-------|----------|-------------|
| `ontology_term` | no | Ontology reference for the entity |
| `description` | no | Human-readable description |
| `fields` | yes | List of field definitions |
| `example` | no | Example values (for documentation) |

## Fields

Fields define the data attributes within an entity.

### Label Convention

**The first field's value is used as the entity's display label.** This applies to:

- Node labels in graph visualization
- Tree view labels in the UI
- Entity identification in references

Place the field that best identifies the entity first in the field list. This could be `name`, `identifier`, `alias`, `title`, or any other field appropriate for the metadata model:

```yaml
# ENA uses 'alias' as the identifying field
fields:
  - name: alias         # First field → used as label
    type: string
    required: true
  - name: accession
    type: string

# MIAPPE uses 'name'
fields:
  - name: name          # First field → used as label
    type: string
    required: true
  - name: description
    type: string
```

This convention keeps specs aligned with the actual metadata standard while providing consistent UI behavior.

```yaml
fields:
  - name: latitude
    type: float
    required: true
    description: Geographic latitude in decimal degrees
    ontology_term: WGS84:lat
    constraints:
      minimum: -90.0
      maximum: 90.0
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Field identifier (snake_case) |
| `type` | yes | Data type (see Field Types) |
| `required` | no | Whether mandatory (default: false) |
| `description` | no | Human-readable description |
| `ontology_term` | no | Semantic ontology reference (e.g., `MIAPPE:DM-1`) |
| `ontologies` | no | List of OLS IDs to search for `ontology_term` type fields |
| `constraints` | no | Validation constraints |
| `items` | conditional | Element type for `list` or target for `entity` |
| `reference` | no | Entity reference in format "Entity.field" (see Relationships) |
| `unique_within` | no | Uniqueness scope: "parent" or "global" |
| `dcat` | no | DCAT/DCAT-AP property this root-entity field maps to (see DCAT Mapping) |

## Field Types

| Type | Description | Python Type | Example |
|------|-------------|-------------|---------|
| `string` | Text value | `str` | `"hello"` |
| `integer` | Whole number | `int` | `42` |
| `float` | Decimal number | `float` | `3.14` |
| `boolean` | True/false | `bool` | `true` |
| `date` | ISO 8601 date | `datetime.date` | `"2024-03-15"` |
| `datetime` | ISO 8601 datetime | `datetime.datetime` | `"2024-03-15T14:30:00"` |
| `uri` | Valid URI/URL | `pydantic.AnyUrl` | `"https://example.org"` |
| `ontology_term` | Ontology reference | `str` | `"GO:0008150"` |
| `list` | Collection | `list[Any]` | See below |
| `entity` | Single nested object | `Any` | See below |

`uri` maps to `AnyUrl` (not `HttpUrl`), so `ftp://` and `mailto:` are accepted.
`list` is `list[Any]` — the `items` type does not enter the annotation; `entity`
maps to `Any`, not a generated nested model.

### Ontology Term Fields

Fields with `type: ontology_term` enable OLS4 (Ontology Lookup Service) integration in the UI. Use the optional `ontologies` field to scope lookups to specific ontologies:

```yaml
# Search only Plant Ontology
- name: tissue
  type: ontology_term
  ontologies: ["po"]
  description: Plant tissue type

# Search multiple ontologies
- name: trait
  type: ontology_term
  ontologies: ["pato", "to"]
  description: Trait from PATO or Trait Ontology

# Search all ontologies (default when ontologies not specified)
- name: any_term
  type: ontology_term
  description: Any ontology term
```

The `ontologies` field accepts a list of OLS IDs (e.g., `po`, `pato`, `ncbitaxon`). When omitted, searches across all available ontologies.

See [Ontology Lookup Guide](../guides/ontology-lookup.md) for details on autocomplete, modal search, and configuration.

### DCAT Mapping

*(spec_version 0.5+)*

The optional `dcat` annotation declares which [DCAT](https://www.w3.org/TR/vocab-dcat-3/) / DCAT-AP property a field provides when a dataset is described as a catalog "card" for discovery (e.g. for a data portal or a FAIR-assessment tool). It is the discovery-layer analogue of `ontology_term`: where `ontology_term` says what a field *means* semantically, `dcat` says what catalog property it *fills*.

The annotation is only read on the **profile's root entity** (the dataset-level container, e.g. `Investigation` for MIAPPE/ISA, `Study` for ENA). Annotations on non-root entities are ignored.

Supported terms and the DCAT Dataset property each fills:

| `dcat` value | Fills | Expected field shape |
|--------------|-------|----------------------|
| `dct:identifier` | dataset identifier | scalar |
| `dct:title` | title | scalar |
| `dct:description` | description | scalar |
| `dct:issued` | issued date | scalar (date) |
| `dct:license` | license | scalar (URI or string) |
| `dct:accessRights` | access rights | scalar |
| `dct:publisher` | publisher name | scalar |
| `dct:relation` | related resources (e.g. publications) | scalar or list |
| `dcat:contactPoint` | contact point | a list of contact objects (`name`/`email`) |
| `dcat:keyword` | keywords | scalar or list |
| `dcat:theme` | themes | scalar or list |
| `dcat:landingPage` | landing page | scalar (URI) |

Example — a MIAPPE `Investigation` root entity:

```yaml
- name: title
  type: string
  dcat: dct:title
- name: submission_date
  type: date
  dcat: dct:issued
- name: license
  type: uri
  dcat: dct:license
- name: contacts
  type: list
  items: Person
  dcat: dcat:contactPoint
```

Profiles whose root entity is a single record rather than a dataset container (e.g. Darwin Core `Occurrence`) have no dataset-level fields to annotate; their card metadata comes instead from an explicit, dataset-level catalog-metadata block. Explicit catalog metadata also overrides any value derived from an annotation.

See [DCAT Export](../architecture/dcat.md) for the full mapping, serialization (JSON-LD / Turtle), and the in-app viewer.

### List Fields

Lists contain multiple items. Use `items` to specify the element type:

```yaml
# List of strings
- name: keywords
  type: list
  items: string

# List of nested entities
- name: samples
  type: list
  items: Sample
```

### Entity Fields

Single nested object (one-to-one relationship):

```yaml
- name: location
  type: entity
  items: Location
```

## Constraints

Constraints define validation rules for individual fields. Different constraints apply to different field types.

### String Constraints

```yaml
- name: identifier
  type: string
  constraints:
    pattern: "^[A-Z]{2}[0-9]{4}$"  # Regex pattern
    min_length: 1                   # Minimum characters
    max_length: 100                 # Maximum characters
    enum: ["draft", "submitted"]    # Allowed values
```

| Constraint | Description |
|------------|-------------|
| `pattern` | Regular expression the value must match |
| `min_length` | Minimum character count |
| `max_length` | Maximum character count |
| `enum` | List of allowed values |

Common patterns:
- Email: `^[\w.-]+@[\w.-]+\.[a-z]{2,}$`
- URL: `^https?://.*`
- ORCID: `^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$`
- DOI: `^10\.\d{4,}/.*$`

### Numeric Constraints

```yaml
- name: temperature
  type: float
  constraints:
    minimum: -273.15  # Absolute zero
    maximum: 1000.0
```

| Constraint | Description |
|------------|-------------|
| `minimum` | Inclusive lower bound |
| `maximum` | Inclusive upper bound |

### List Constraints

```yaml
- name: keywords
  type: list
  items: string
  constraints:
    min_items: 1   # At least one keyword
    max_items: 10  # Maximum 10 keywords
```

| Constraint | Description |
|------------|-------------|
| `min_items` | Minimum number of items |
| `max_items` | Maximum number of items |

### Constraints by Field Type

| Field Type | Available Constraints |
|------------|----------------------|
| `string` | pattern, min_length, max_length, enum |
| `integer`, `float` | minimum, maximum |
| `list` | min_items, max_items |
| `uri`, `ontology_term`, `boolean`, `date`, `datetime`, `entity` | none (field-level) |

A field-level `pattern` **constraint** is applied by the model factory only to
`string` fields — Pydantic cannot compile a regex constraint onto a `uri`
(`AnyUrl`) field, so declaring one there makes the field reject every value. A
`pattern` on a `uri`/`ontology_term` field is instead enforced by a **rule** (see
[Validation Rules](#validation-rules)): the validation engine runs a
`PatternRule` for such rules, while a rule `pattern` on a `string` field is merged
onto the field and enforced by Pydantic. A `pattern` rule on a `date`/`datetime`
field is not enforced (the field's own date parsing applies).

## Relationships

### Hierarchical (Parent-Child)

Use `list` type in the parent to embed children, and `reference` in the child to link back:

```yaml
entities:
  Investigation:
    fields:
      - name: identifier
        type: string
        required: true
      - name: studies
        type: list
        items: Study

  Study:
    fields:
      - name: identifier
        type: string
        required: true
      - name: investigation_id
        type: string
        required: true
        reference: Investigation.identifier
```

The `reference` field:
- Links child entities to their parent
- Auto-filled from parent context when editing nested data
- Visible in flat exports (Excel, CSV)
- Used for MCP auto-detection of parent relationships

### Entity References

Use `reference` for any entity-to-entity link:

```yaml
- name: protocol_id
  type: string
  reference: Protocol.name
```

This validates that the referenced entity exists and enables auto-linking.

### One-to-One Embedding

Use `entity` type for single nested objects:

```yaml
- name: measurement_type
  type: entity
  items: OntologyAnnotation
```

## Validation: Field Constraints vs Rules

Metaseed provides two validation mechanisms. Choose based on your needs:

### Field Constraints (Pydantic Layer)

Use for **single-field** validation at **model creation time**:

- Pattern matching (regex)
- Numeric ranges (min/max)
- Enum/vocabulary restrictions
- String length limits
- List item counts

```yaml
fields:
  - name: latitude
    type: float
    constraints:
      minimum: -90
      maximum: 90

  - name: status
    type: string
    constraints:
      enum: ["draft", "submitted", "published"]

  - name: email
    type: string
    constraints:
      pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
```

Field constraints are enforced by Pydantic when creating model instances. Invalid data raises a validation error immediately.

### Validation Rules (Engine Layer)

Use for **cross-field** or **cross-entity** validation:

- Date range comparisons (start before end)
- Conditional requirements (A OR B)
- Coordinate pairs (lat/lon together)
- Uniqueness constraints
- Reference integrity

```yaml
validation_rules:
  - name: date_range
    type: date_range
    applies_to: [Study]
    start_field: start_date
    end_field: end_date
    message: "Study end date cannot be before start date"

  - name: coordinates_together
    type: coordinate_pair
    applies_to: [Location]
    lat_field: latitude
    lon_field: longitude

  - name: identifier_unique
    type: uniqueness
    applies_to: all
    field: identifier
    unique_within: parent
```

Validation rules run after model creation via the validation engine. They can check relationships between fields and entities.

### When to Use Which

| Scenario | Use |
|----------|-----|
| Email format | Field constraint (`pattern`) |
| Latitude range | Field constraint (`minimum`, `maximum`) |
| Status vocabulary | Field constraint (`enum`) |
| End date after start date | Validation rule (`date_range`) |
| Either DOI or PubMed ID required | Validation rule (`conditional`) |
| Lat/lon both present or both absent | Validation rule (`coordinate_pair`) |
| Unique identifier within parent | Validation rule (`uniqueness`) |
| Reference points to existing entity | Validation rule (`reference`) |

## Validation Rules

Validation rules define cross-field or cross-entity constraints.

```yaml
validation_rules:
  # Explicit type (recommended)
  - name: study_date_range
    type: date_range
    applies_to: [Study]
    start_field: start_date
    end_field: end_date
    message: "End date must be after start date"

  # Conditional requirement
  - name: publication_identifier
    type: conditional
    description: Must have doi, pubmed_id, or title
    applies_to: [Publication]
    condition: "doi OR pubmed_id OR title"

  # Coordinate pair
  - name: location_coordinates
    type: coordinate_pair
    applies_to: [Location]
    lat_field: latitude
    lon_field: longitude

  # Cardinality
  - name: at_least_one_sample
    type: cardinality
    applies_to: [Study]
    field: samples
    min_items: 1

  # Uniqueness
  - name: unique_sample_id
    type: uniqueness
    applies_to: [Sample]
    field: identifier
    unique_within: parent

  # Referential integrity
  - name: protocol_exists
    type: reference
    applies_to: [Process]
    field: executes_protocol
    reference: Protocol.name
```

### Rule Types

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `conditional` | Boolean condition (A OR B, A AND B) | `condition` |
| `date_range` | Date comparison | `start_field`, `end_field` (or `condition`) |
| `coordinate_pair` | Lat/lon pair validation | `lat_field`, `lon_field` (optional, defaults to latitude/longitude) |
| `cardinality` | List min/max items | `field`, `min_items` and/or `max_items` |
| `uniqueness` | Unique within scope | `field`, `unique_within` |
| `reference` | Entity reference integrity | `field`, `reference` |

### Rule Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Rule identifier |
| `type` | no | Explicit rule type (recommended). If omitted, inferred from other fields |
| `description` | no | What the rule checks |
| `message` | no | Custom error message (overrides default) |
| `applies_to` | no | Entity names or `"all"` (default: `"all"`) |
| `field` | conditional | Target field for single-field rules |
| `condition` | conditional | Boolean condition expression |
| `reference` | conditional | Entity.field for integrity checks |
| `unique_within` | conditional | `"parent"` or `"global"` for uniqueness scope |
| `min_items` | no | Minimum list items (cardinality) |
| `max_items` | no | Maximum list items (cardinality) |
| `start_field` | conditional | Start field for date_range |
| `end_field` | conditional | End field for date_range |
| `lat_field` | no | Latitude field for coordinate_pair (default: `latitude`) |
| `lon_field` | no | Longitude field for coordinate_pair (default: `longitude`) |

### Condition Syntax

Conditions use field names with boolean operators:

```
field_name                    # True if field has value
NOT field_name                # True if field is empty
field1 AND field2             # Both have values
field1 OR field2              # At least one has value
(a AND b) OR (NOT a AND NOT b)  # Complex logic
field1 >= field2              # Comparison (dates, numbers)
```

### Backward Compatibility

Rules without a `type` field continue to work. The engine infers the type from other fields:

- `condition` with comparison operators -> `date_range`
- `condition` with lat/lon fields -> `coordinate_pair`
- `condition` with AND/OR -> `conditional`
- `min_items`/`max_items` with `field` -> `cardinality`
- `unique_within` with `field` -> `uniqueness`
- `reference` with `field` -> `reference`

Using explicit `type` is recommended for clarity and to avoid ambiguity.

## Design Patterns

### Field Ordering

Place the most identifying field first in each entity's field list. The first field's value is used as the display label throughout the UI:

```yaml
fields:
  - name: name            # First → display label
    type: string
    required: true
  - name: description
    type: string
  - name: other_fields
    type: string
```

Use whatever field name fits the metadata standard (`name`, `identifier`, `alias`, `title`, etc.).

### Ontology Linking

Link fields to ontology terms for semantic interoperability:

```yaml
- name: organism
  type: string
  ontology_term: NCBITAXON:organism
  description: Scientific name of the organism
```

### Common Field Patterns

```yaml
# Email with validation
- name: email
  type: string
  constraints:
    pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"

# ORCID identifier
- name: orcid
  type: string
  constraints:
    pattern: "^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$"

# DOI
- name: doi
  type: string
  constraints:
    pattern: "^10\\.[0-9]{4,}/.*$"

# Controlled vocabulary
- name: status
  type: string
  constraints:
    enum: ["draft", "submitted", "published", "archived"]

# Geographic coordinates
- name: latitude
  type: float
  constraints:
    minimum: -90.0
    maximum: 90.0

- name: longitude
  type: float
  constraints:
    minimum: -180.0
    maximum: 180.0
```

## Load-bearing behaviors and limitations

Behaviors that affect how specs are interpreted but are easy to miss:

- **`codename`** (on `FieldSpec`) — an alternative identifier used for import
  column matching (`agent/mapping.py`), MCP field info, and ISA-Tab export. Its
  format varies by profile (camelCase in MIAPPE, CURIEs in DiSSCo, XML tags in
  ENA). Fields with no `codename` map source columns less well.
- **`seek`** (on `EntityDefSpec`, a `SeekEntityConfig`) — routing metadata for the
  SEEK exporter (e.g. an entity's JERM role). Absent from most profiles.
- **`UniqueIdPatternRule`** — the engine automatically imposes
  `^[A-Za-z0-9_-]+$` on any field named `unique_id` **or** `identifier`. This
  conflicts with DOI- or URI-shaped identifiers; name such a field something else
  or override with an explicit `pattern` rule.
- **Rule-level pattern merge** — a `pattern`/`enum`/`minimum`/`maximum` declared on
  a `validation_rule` is copied onto the matching field for Pydantic enforcement
  **only when the field is `string`/`integer`/`float`**; on other field types the
  merge is skipped (uri/ontology_term patterns are enforced by the engine
  instead, dates by the field's own parsing).
- **Not yet implemented** — `type: reference` rules and the field-level
  `unique_within` attribute are parsed but not enforced (dataset-scope reference
  integrity is handled separately by `DatasetValidator`; use a rule-level
  `unique_within` for uniqueness). An unknown rule `type:` raises `ValueError`
  rather than being silently ignored.
- **Defaults** — a profile's `entities` and an entity's `fields` are optional
  (default `{}` / `[]`); `enum` on a `list` field builds `list[Literal[...]]`; and
  every `required: true` field also gets an engine-level required-fields check on
  top of the Pydantic one.

## File Organization

Specs are stored as YAML files:

```
src/metaseed/specs/
├── miappe/
│   └── 1.2/
│       └── profile.yaml
├── isa/
│   └── 1.0/
│       └── profile.yaml
└── custom/
    └── 1.0/
        └── profile.yaml
```

User-created specs are saved to:
- Linux/macOS: `~/.local/share/metaseed/specs/`
- Windows: `%LOCALAPPDATA%/metaseed/specs/`

## Best Practices

1. **Use descriptive names**: Field names should clearly indicate their purpose.

2. **Add descriptions**: Help users understand what each field expects.

3. **Link to ontologies**: Improve semantic interoperability.

4. **Start minimal**: Add only needed fields. Extend later as requirements emerge.

5. **Use validation rules**: Catch errors early with patterns and constraints.

6. **Follow naming conventions**:
   - Entities: PascalCase (`BiologicalMaterial`)
   - Fields: snake_case (`collection_date`)
   - Profile names: lowercase with hyphens (`my-profile`)

7. **Test with examples**: Include `example` values in entities to verify your schema works.

## See Also

- [Quick Start](../getting-started/quickstart.md) - Launch the web UI with `metaseed ui`
- [Spec Builder Tutorial](../guides/spec-builder.md) - Visual tool for creating specs
- [Model Factory](../architecture/model-factory.md) - How specs become Pydantic models
- [Profiles](../profiles/isa.md) - Available built-in profiles
