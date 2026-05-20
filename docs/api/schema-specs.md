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
| `ontology_term` | no | Ontology reference |
| `constraints` | no | Validation constraints |
| `items` | conditional | Element type for `list` or target for `entity` |
| `parent_ref` | no | Parent entity reference (see Relationships) |
| `reference` | no | Foreign key reference (see Relationships) |
| `unique_within` | no | Uniqueness scope: "parent" or "global" |

## Field Types

| Type | Description | Python Type | Example |
|------|-------------|-------------|---------|
| `string` | Text value | `str` | `"hello"` |
| `integer` | Whole number | `int` | `42` |
| `float` | Decimal number | `float` | `3.14` |
| `boolean` | True/false | `bool` | `true` |
| `date` | ISO 8601 date | `datetime.date` | `"2024-03-15"` |
| `datetime` | ISO 8601 datetime | `datetime.datetime` | `"2024-03-15T14:30:00"` |
| `uri` | Valid URI/URL | `pydantic.HttpUrl` | `"https://example.org"` |
| `ontology_term` | Ontology reference | `str` | `"GO:0008150"` |
| `list` | Collection | `list[T]` | See below |
| `entity` | Single nested object | nested model | See below |

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

Constraints define validation rules for individual fields.

```yaml
constraints:
  pattern: "^[A-Z]{2}[0-9]{4}$"    # Regex pattern
  min_length: 1                     # Minimum string length
  max_length: 100                   # Maximum string length
  minimum: 0                        # Minimum numeric value
  maximum: 100                      # Maximum numeric value
  min_items: 1                      # Minimum list items
  max_items: 10                     # Maximum list items
  enum: ["draft", "submitted", "published"]  # Allowed values
```

| Constraint | Applies To | Description |
|------------|------------|-------------|
| `pattern` | string | Regex pattern |
| `min_length` | string | Minimum length |
| `max_length` | string | Maximum length |
| `minimum` | integer, float | Minimum value (inclusive) |
| `maximum` | integer, float | Maximum value (inclusive) |
| `min_items` | list | Minimum items |
| `max_items` | list | Maximum items |
| `enum` | string | List of allowed values |

## Relationships

### Hierarchical (Parent-Child)

Use `list` type to embed children within a parent:

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
        parent_ref: Investigation.identifier
```

The `parent_ref` field is:
- Auto-filled from parent context when editing nested data
- Hidden in nested forms (the relationship is implicit)
- Visible in flat exports (Excel, CSV)

### Foreign Key Reference

Use `reference` for relational-style links:

```yaml
- name: protocol_id
  type: string
  reference: Protocol.name
```

This validates that the referenced Protocol exists.

### One-to-One Embedding

Use `entity` type for single nested objects:

```yaml
- name: measurement_type
  type: entity
  items: OntologyAnnotation
```

## Validation Rules

Validation rules define cross-field or cross-entity constraints.

```yaml
validation_rules:
  # Pattern validation
  - name: email_format
    applies_to: [Person]
    field: email
    pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"

  # Conditional requirement
  - name: publication_identifier
    description: Must have doi, pubmed_id, or title
    applies_to: [Publication]
    condition: "doi OR pubmed_id OR title"

  # Cross-field validation
  - name: date_range
    description: End date must be after start date
    applies_to: [Study]
    condition: "end_date >= start_date"

  # Cardinality
  - name: at_least_one_sample
    applies_to: [Study]
    field: samples
    min_items: 1

  # Referential integrity
  - name: protocol_exists
    applies_to: [Process]
    field: executes_protocol
    reference: Protocol.name
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Rule identifier |
| `description` | no | What the rule checks |
| `applies_to` | no | Entity names or `"all"` (default: `"all"`) |
| `field` | no | Specific field for single-field rules |
| `condition` | no | Boolean condition expression |
| `pattern` | no | Regex for pattern validation |
| `minimum` | no | Min value for range validation |
| `maximum` | no | Max value for range validation |
| `enum` | no | Allowed values |
| `reference` | no | Entity.field for integrity checks |
| `unique_within` | no | `"parent"` = unique within parent |
| `min_items` | no | Minimum list items |
| `max_items` | no | Maximum list items |

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

## Design Patterns

### Identifier Fields

Most entities need an identifier:

```yaml
- name: identifier
  type: string
  required: true
  unique_within: parent
  description: Unique identifier within this context
```

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

- [Spec Builder Tutorial](../guides/spec-builder.md) - Visual tool for creating specs
- [Model Factory](../architecture/model-factory.md) - How specs become Pydantic models
- [Profiles](../profiles/isa.md) - Available built-in profiles
