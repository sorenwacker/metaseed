# MetaseedClient API

`MetaseedClient` is the recommended entry point for programmatic use of metaseed. It provides a clean, stable API for working with metadata schemas, creating entities, and validating data.

## Quick Start

```python
from metaseed import MetaseedClient

# Create a client for a specific profile
client = MetaseedClient("miappe", "1.2")

# Create entities
inv = client.create_entity("Investigation", {
    "unique_id": "INV-001",
    "title": "Drought Tolerance Study"
})

study = client.create_entity("Study", {
    "unique_id": "STU-001",
    "title": "Field Trial 2024"
}, parent_id=inv.id)

# Validate all entities
result = client.validate()
if not result.valid:
    for issue in result.issues:
        print(f"{issue.field}: {issue.message}")

# Serialize for storage
data = client.serialize()
```

## Creating a Client

### From a profile name

```python
# Use latest version
client = MetaseedClient("miappe")

# Specify version
client = MetaseedClient("miappe", "1.2")
client = MetaseedClient("isa", "1.0")
client = MetaseedClient("ena", "1.0")
```

### From a custom spec

Use `from_spec()` when working with custom or dynamically-generated schemas:

```python
spec = {
    "version": "1.0",
    "name": "custom-profile",
    "entities": {
        "Sample": {
            "description": "A biological sample",
            "fields": [
                {"name": "id", "type": "string", "required": True, "description": "Unique ID"},
                {"name": "name", "type": "string", "required": False, "description": "Display name"}
            ]
        }
    }
}

client = MetaseedClient.from_spec(spec)
```

## Entity CRUD Operations

### Create

```python
entity = client.create_entity("Investigation", {
    "unique_id": "INV-001",
    "title": "My Study"
})

# With parent relationship
child = client.create_entity("Study", {
    "unique_id": "STU-001",
    "title": "Child Study",
    "investigation_id": "INV-001"
}, parent_id=entity.id)
```

### Permissive Mode (skip_validation)

For progressive editing where users fill in fields over multiple sessions:

```python
# Create draft with incomplete data (skips Pydantic validation)
draft = client.create_entity(
    "Investigation",
    {"title": "Work in progress"},  # missing required unique_id
    skip_validation=True,
)

# Update draft without validation
client.update_entity(
    draft.id,
    {"title": "Still working on it"},
    skip_validation=True,
)

# Validate when ready to check for issues
result = client.validate_entity(draft.id)
if not result.valid:
    for issue in result.issues:
        print(f"Warning: {issue.field}: {issue.message}")
```

This is useful for web forms where:
- Users create entities with minimal data
- Fields are filled in over multiple sessions
- Validation warnings are shown but don't block saving

### Read

```python
entity = client.get_entity(entity_id)

print(entity.id)
print(entity.entity_type)
print(entity.data)
print(entity.label)  # Derived display label
print(entity["unique_id"])  # Subscript access
```

### Update

```python
entity = client.update_entity(entity_id, {
    "unique_id": "INV-001",
    "title": "Updated Title"
})
```

### Delete

```python
client.delete_entity(entity_id)
```

## Tree Navigation

```python
# Get complete tree
tree = client.get_tree()
for node in tree:
    print(f"{node.entity_type}: {node.label}")
    for child in node.children:
        print(f"  - {child.label}")

# Get root entities only
roots = client.get_roots()

# Get children of a specific entity
children = client.get_children(parent_id)

# Get label for an entity
label = client.get_entity_label(entity_id)
```

## Serialization

### Save

```python
import json

# Default flat format (list of entities with _type metadata)
data = client.serialize()

# Tree format (nested hierarchy with labels)
data = client.serialize(format="tree")

with open("dataset.json", "w") as f:
    json.dump(data, f, indent=2)
```

### Load

```python
with open("dataset.json") as f:
    data = json.load(f)

# Auto-detects format (flat or tree)
client.load(data)

# Load from YAML file
client.load_yaml("dataset.yaml")
```

### Serialization Formats

**Flat format** (default):
```json
{
  "profile": "miappe",
  "version": "1.2",
  "entities": [
    {"_type": "Investigation", "unique_id": "INV-1", "title": "..."},
    {"_type": "Study", "unique_id": "STU-1", "_parent_unique_id": "INV-1"}
  ]
}
```

**Tree format**:
```json
{
  "profile": "miappe",
  "version": "1.2",
  "tree": [
    {
      "id": "node-1",
      "entity_type": "Investigation",
      "label": "INV-1",
      "data": {"unique_id": "INV-1", "title": "..."},
      "children": [...]
    }
  ]
}
```

### Clear

```python
client.clear()
```

## Validation

### Validate all entities

```python
result = client.validate()

if result.valid:
    print("All entities valid")
else:
    for issue in result.issues:
        print(f"{issue.field}: {issue.message} (rule: {issue.rule})")
```

### Validate a specific entity

```python
result = client.validate_entity(entity_id)

# Use ValidationResult as bool
if result:
    print("Valid")
else:
    print(f"Found {result.error_count} errors")

# Get errors for a specific field
field_errors = result.get_field_errors("title")
```

## Schema Introspection

### List entity types

```python
types = client.list_entity_types()
# ['Investigation', 'Study', 'Person', 'Sample', ...]
```

### Get field information

```python
fields = client.get_entity_fields("Investigation")

for field in fields:
    status = "(required)" if field.required else ""
    print(f"{field.name}: {field.type} {status}")
    print(f"  {field.description}")
```

### Get complete schema

```python
schema = client.get_entity_schema("Investigation")

print(f"Entity: {schema.name}")
print(f"Description: {schema.description}")
print(f"Required fields: {schema.required_fields}")
print(f"Optional fields: {schema.optional_fields}")
```

## Error Handling

All errors inherit from `MetaseedError`:

```python
from metaseed import (
    MetaseedError,
    ProfileNotFoundError,
    EntityNotFoundError,
    EntityTypeNotFoundError,
)

try:
    client = MetaseedClient("invalid-profile")
except ProfileNotFoundError as e:
    print(f"Profile not found: {e.profile}")

try:
    entity = client.get_entity("invalid-id")
except EntityNotFoundError as e:
    print(f"Entity not found: {e.entity_id}")

try:
    client.create_entity("InvalidType", {})
except EntityTypeNotFoundError as e:
    print(f"Type {e.entity_type} not in {e.profile}")

# Catch all metaseed errors
try:
    ...
except MetaseedError as e:
    print(f"Metaseed error: {e}")
```

## Domain Objects

### Entity

Represents a stored entity instance:

```python
entity.id           # Unique identifier
entity.entity_type  # Type name (e.g., "Investigation")
entity.data         # Field values dict
entity.parent_id    # Parent entity ID or None
entity.label        # Derived display label
entity.get("field", default)  # Get field with default
entity["field"]     # Get field (raises KeyError if missing)
```

### EntityNode

Represents an entity in the tree hierarchy:

```python
node.id             # Unique identifier
node.entity_type    # Type name
node.label          # Display label
node.has_children   # Boolean
node.children       # List of child EntityNodes
node.to_dict()      # Convert to dictionary
```

### FieldInfo

Describes an entity field:

```python
field.name          # Field name
field.type          # Type string (e.g., "string", "list")
field.required      # Boolean
field.description   # Human-readable description
field.ontology_term # Optional ontology reference
field.items         # Item type for lists
field.constraints   # Validation constraints dict
```

### EntitySchema

Complete schema for an entity type:

```python
schema.name           # Entity name
schema.description    # Description
schema.ontology_term  # Optional ontology reference
schema.fields         # Tuple of FieldInfo
schema.required_fields   # Tuple of required field names
schema.optional_fields   # Tuple of optional field names
schema.all_field_names   # All field names
```

### ValidationResult

Result of validation:

```python
result.valid        # Boolean
result.issues       # List of ValidationIssue
result.error_count  # Number of issues
bool(result)        # True if valid
result.get_field_errors("field")  # Filter issues by field
```

### ValidationIssue

A single validation issue:

```python
issue.field    # Field path
issue.message  # Error message
issue.rule     # Rule that triggered the issue
```

## Comparison with ProfileFacade

| Feature | MetaseedClient | ProfileFacade |
|---------|---------------|---------------|
| Primary use | Programmatic API | Interactive/Jupyter |
| Entity storage | Built-in | Built-in |
| Tab completion | No | Yes |
| Direct model creation | No | Yes (`facade.Investigation(...)`) |
| Schema introspection | `get_entity_fields()` | `helper.field_info()` |
| Validation | `validate()` | Manual via validators |

For interactive use in Jupyter notebooks, the `ProfileFacade` convenience functions (`miappe()`, `isa()`, etc.) may be more convenient due to their tab-completion support.
