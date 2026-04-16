# Schema Specifications

Schema specifications define metadata structure using YAML files. This page documents all available options.

## Profile Structure

A profile spec contains all entities for a metadata standard:

```yaml
name: MyProfile
version: "1.0"
description: Description of the profile
ontology: PPEO

entities:
  Investigation:
    # entity definition...
  Study:
    # entity definition...

validation_rules:
  - name: rule_name
    # rule definition...
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Profile name |
| `version` | yes | Version string |
| `description` | no | Profile description |
| `ontology` | no | Base ontology (e.g., PPEO, OBI) |
| `entities` | yes | Dictionary of entity definitions |
| `validation_rules` | no | Cross-entity validation rules |

## Entity Definition

```yaml
entities:
  Investigation:
    ontology_term: OBI:0000066
    description: A scientific investigation
    fields:
      - name: unique_id
        # field definition...
    example:
      unique_id: "INV001"
      title: "Example investigation"
```

| Field | Required | Description |
|-------|----------|-------------|
| `ontology_term` | no | Ontology reference for the entity |
| `description` | no | Human-readable description |
| `fields` | yes | List of field definitions |
| `example` | no | Example values for documentation |

## Field Definition

```yaml
fields:
  - name: latitude
    type: float
    required: true
    description: Geographic latitude
    ontology_term: WGS84:lat
    constraints:
      minimum: -90.0
      maximum: 90.0
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Field identifier (snake_case) |
| `type` | yes | Data type (see below) |
| `required` | no | Whether field is mandatory (default: false) |
| `description` | no | Human-readable description |
| `ontology_term` | no | Ontology reference |
| `items` | no | Element type for `list` or `entity` types |
| `constraints` | no | Validation constraints |
| `parent_ref` | no | Parent entity reference (see below) |

## Parent Reference Fields

Fields that reference a parent entity can be marked with `parent_ref`. These fields are:

- Auto-filled based on parent context when editing nested entities
- Hidden from nested forms (since the relationship is implicit in the nesting)
- Visible only in flat exports (Excel, CSV) where nesting is lost

```yaml
fields:
  - name: study_id
    type: string
    required: true
    parent_ref: Study.identifier
    description: Reference to the parent Study
```

The format is `EntityType.field_name` where:
- `EntityType` is the parent entity type (e.g., `Study`, `Investigation`)
- `field_name` is the field used as identifier (e.g., `identifier`, `unique_id`)

## Field Types

| Type | Description | Python Type |
|------|-------------|-------------|
| `string` | Text value | `str` |
| `integer` | Whole number | `int` |
| `float` | Decimal number | `float` |
| `boolean` | True/false | `bool` |
| `date` | ISO 8601 date | `datetime.date` |
| `datetime` | ISO 8601 datetime | `datetime.datetime` |
| `uri` | Valid URI/URL | `pydantic.HttpUrl` |
| `ontology_term` | Ontology reference | `str` |
| `list` | Collection | `list[T]` (use `items` for element type) |
| `entity` | Single nested entity | nested model (use `items` for entity name) |

## Constraints

```yaml
constraints:
  pattern: "^[A-Z]{2}[0-9]{4}$"
  min_length: 1
  max_length: 100
  minimum: 0
  maximum: 100
  enum: ["draft", "submitted", "published"]
```

| Constraint | Applies To | Description |
|------------|------------|-------------|
| `pattern` | string | Regex pattern |
| `min_length` | string | Minimum length |
| `max_length` | string | Maximum length |
| `minimum` | integer, float | Minimum value (inclusive) |
| `maximum` | integer, float | Maximum value (inclusive) |
| `enum` | string | List of allowed values |

## Validation Rules

For cross-field or cross-entity validation:

```yaml
validation_rules:
  - name: date_range_valid
    description: End date must be after start date
    applies_to: [Study]
    condition: "end_date >= start_date"

  - name: coordinates_complete
    description: Both lat and lon required together
    applies_to: [Location]
    condition: "(latitude AND longitude) OR (NOT latitude AND NOT longitude)"

  - name: unique_id
    description: Identifier must be unique within parent
    applies_to: [Sample]
    field: identifier
    unique_within: parent
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Rule identifier |
| `description` | no | What the rule checks |
| `applies_to` | no | Entity names or `"all"` (default: `"all"`) |
| `field` | no | Specific field for single-field rules |
| `condition` | no | Condition expression (see syntax below) |
| `pattern` | no | Regex for pattern rules |
| `minimum` | no | Min value for range rules |
| `maximum` | no | Max value for range rules |
| `enum` | no | Allowed values |
| `reference` | no | Entity.field for reference integrity |
| `unique_within` | no | `"parent"` = unique within parent entity |
| `min_items` | no | Minimum list items |
| `max_items` | no | Maximum list items |

### Condition Syntax

Conditions use field names with boolean operators:

| Operator | Description | Example |
|----------|-------------|---------|
| `AND` | Both must be true | `latitude AND longitude` |
| `OR` | Either can be true | `doi OR pubmed_id OR title` |
| `NOT` | Negation | `NOT trait_accession_number` |
| `>=`, `<=` | Comparison | `end_date >= start_date` |
| `()` | Grouping | `(a AND b) OR (NOT a AND NOT b)` |

A field name alone evaluates to true if the field has a value.

## See Also

- [Profiles](../profiles/isa.md) - Available metadata profiles
- [Model Factory](../architecture/model-factory.md) - How specs become Pydantic models
