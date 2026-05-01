# Spec Builder Tutorial

The Spec Builder is a visual tool for creating custom profile specifications. It provides an ERD-style canvas for designing entities and their relationships.

## Accessing the Spec Builder

1. Start the Metaseed server: `metaseed serve`
2. Navigate to `http://localhost:8765/spec-builder`

## Creating a New Specification

### Start from Scratch

Click **Start from Scratch** to create an empty specification.

### Clone a Template

Select a built-in profile (MIAPPE, ISA, etc.) as a starting point. This copies all entities and fields, which you can then modify.

## Core Concepts

### Entities

Entities are the main data structures in your specification (e.g., Project, Investigation, Sample). Each entity has:

- **Name**: PascalCase identifier (e.g., `BiologicalMaterial`)
- **Description**: Human-readable explanation
- **Fields**: The data fields this entity contains

### Fields

Fields define the data within an entity. Each field has:

| Property | Description |
|----------|-------------|
| Name | snake_case identifier (e.g., `sample_id`) |
| Type | Data type (see below) |
| Required | Whether the field must have a value |
| Description | Human-readable explanation |
| Items/Target | For `list` and `entity` types, the target entity |

### Field Types

| Type | Description | Items/Target |
|------|-------------|--------------|
| `string` | Text value | - |
| `integer` | Whole number | - |
| `float` | Decimal number | - |
| `boolean` | True/false | - |
| `date` | Date (YYYY-MM-DD) | - |
| `datetime` | Date and time | - |
| `uri` | URL or URI | - |
| `ontology_term` | Ontology reference | - |
| `list` | List of items | Entity name or primitive type |
| `entity` | Single nested object | Entity name |

## Modeling Relationships

There are several ways to connect entities:

### 1. Nested Lists (Hierarchical)

Use `type: list` with `Items/Target` set to an entity name.

```yaml
Project:
  fields:
    - name: investigations
      type: list
      items: Investigation
```

This embeds Investigation objects inside Project. Data is hierarchical/nested.

**Use when**: Parent contains children (e.g., Project contains Investigations).

**Auto-created fields**: When you add a list field pointing to another entity, the Spec Builder automatically:

1. Adds an `identifier` field to the parent entity (if missing)
2. Adds a back-reference field to the child entity (e.g., `project_id` with `parent_ref: Project.identifier`)

This ensures children can reference their parent without manual setup.

### 2. Single Nested Entity

Use `type: entity` with `Items/Target` set to an entity name.

```yaml
Sample:
  fields:
    - name: location
      type: entity
      items: Location
```

This embeds a single Location object inside Sample.

**Use when**: One-to-one relationship with embedded data.

### 3. Foreign Key Reference

Use `type: string` with the **Reference** field (under Advanced) set to `Entity.field`.

```yaml
Sample:
  fields:
    - name: location_id
      type: string
      reference: Location.identifier
```

This stores only the ID, with validation that the referenced Location exists.

**Use when**: Relational-style data where entities exist independently.

### 4. Parent Reference (Auto-filled)

Use `type: string` with the **Parent Ref** field (under Advanced) set to `Entity.field`.

```yaml
Investigation:
  fields:
    - name: project_id
      type: string
      parent_ref: Project.identifier
```

This field is automatically filled from the parent context when editing nested data. It's hidden in forms since it's automatic.

**Use when**: Child needs to reference parent, and you want auto-fill behavior.

## Example: Research Project Structure

Here's a typical hierarchical structure:

```yaml
name: research-project
root_entity: Project

entities:
  Project:
    fields:
      - name: identifier
        type: string
        required: true
      - name: title
        type: string
        required: true
      - name: investigations
        type: list
        items: Investigation

  Investigation:
    fields:
      - name: identifier
        type: string
        required: true
      - name: title
        type: string
      - name: studies
        type: list
        items: Study
      - name: contacts
        type: list
        items: Person

  Study:
    fields:
      - name: identifier
        type: string
        required: true
      - name: title
        type: string
      - name: start_date
        type: date
      - name: samples
        type: list
        items: Sample

  Sample:
    fields:
      - name: identifier
        type: string
        required: true
      - name: organism
        type: string
      - name: collection_date
        type: date

  Person:
    fields:
      - name: name
        type: string
        required: true
      - name: email
        type: string
      - name: affiliation
        type: string
```

## Adding Fields via the UI

1. Click an entity in the ERD canvas
2. In the right panel, click **+ Add Field**
3. Enter field name (snake_case)
4. Select field type
5. For `list` or `entity` types, set **Items/Target** to the entity name
6. Click **Save Field**

### Advanced Field Options

Expand the **Advanced** section to access:

- **Ontology**: Link to ontology term (e.g., `MIAPPE:DM-1`)
- **Unique Within**: Enforce uniqueness (`parent` or `global`)
- **Parent Ref**: Auto-fill from parent (`Entity.field`)
- **Reference**: Foreign key validation (`Entity.field`)
- **Constraints**: Pattern, min/max values, allowed values

## Validation Rules

For cross-entity validation, use the **Advanced Rules** section in the sidebar:

- **Required If**: Field is required when another field has a value
- **Unique**: Field must be unique within scope
- **Pattern**: Regex validation
- **Range**: Numeric min/max validation

## Saving and Exporting

### Save

Click **Save** to store your specification. Saved specs appear in "Your Specifications" on the start page.

Specs are saved to:

- Linux/macOS: `~/.local/share/metaseed/specs/`
- Windows: `%LOCALAPPDATA%/metaseed/specs/`

### Export

Click **Export** to download the specification as a YAML file.

### Preview

Click **Preview YAML** to see the generated YAML before saving.

## Common Patterns

### Identifier Fields

Most entities need an identifier:

```yaml
- name: identifier
  type: string
  required: true
  unique_within: global
```

### Required vs Optional

Mark essential fields as required. Optional fields provide flexibility:

```yaml
- name: title
  type: string
  required: true    # Must have a title

- name: description
  type: string
  required: false   # Description is optional
```

### Lists with Constraints

Ensure lists have at least one item:

```yaml
- name: samples
  type: list
  items: Sample
  constraints:
    min_items: 1
```

## Tips

1. **Start with the hierarchy**: Decide which entity is the root and how others nest inside it.

2. **Add identifiers first**: Every entity that will be referenced needs an identifier field.

3. **Use Preview often**: Check the YAML output to verify your structure.

4. **Clone existing profiles**: Start from MIAPPE or ISA to see established patterns.

5. **Keep it simple**: Only add fields you actually need. You can extend later.
