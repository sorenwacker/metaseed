# Facade API

The Facade API provides an interactive interface for exploring and creating metadata entities. It features tab completion, built-in help, and guided entity creation.

## Quick Start

```python
from metaseed import miappe, isa, ProfileFacade

# Use convenience functions
m = miappe()
i = isa()

# Or create directly with explicit version
m = ProfileFacade("miappe", "1.1")
```

## ProfileFacade

`ProfileFacade` is the main entry point for working with a metadata profile.

### Creating a Facade

```python
from metaseed import ProfileFacade

# Load MIAPPE with default version
m = ProfileFacade("miappe")

# Load specific version
m = ProfileFacade("miappe", "1.1")

# Load ISA profile
i = ProfileFacade("isa", "1.0")
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `profile` | `str` | Profile name (e.g., "miappe") |
| `version` | `str` | Profile version (e.g., "1.1") |
| `entities` | `list[str]` | Available entity names |

### Methods

#### `help(entity_name: str | None = None)`

Display help for the profile or a specific entity.

```python
# Profile overview
m.help()

# Entity-specific help
m.help("Investigation")
```

#### `search(query: str) -> list[str]`

Search for entities or fields by keyword (case-insensitive).

```python
results = m.search("date")
# ['Environment.date', 'Event.date', 'Investigation.submission_date', ...]

results = m.search("sample")
# ['ObservationUnit.samples', 'Sample (entity)']
```

### Entity Access

Access entities via attribute lookup. Tab completion works in Jupyter and IPython.

```python
# Direct access
inv_helper = m.Investigation

# Case-insensitive
inv_helper = m.investigation
```

## EntityHelper

Each entity in a profile is wrapped in an `EntityHelper` that provides introspection and creation methods.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Entity name |
| `description` | `str` | Entity description from spec |
| `ontology_term` | `str \| None` | Ontology term for the entity |
| `required_fields` | `list[str]` | Required field names |
| `optional_fields` | `list[str]` | Optional field names |
| `all_fields` | `list[str]` | All field names |
| `nested_fields` | `dict[str, str]` | Fields containing nested entities `{field: entity_type}` |
| `example_data` | `dict[str, Any]` | Example values from spec |

### Field Introspection

#### `field_info(field_name: str) -> dict[str, Any]`

Get detailed information about a field.

```python
info = m.Investigation.field_info("unique_id")
# {
#     'name': 'unique_id',
#     'type': 'string',
#     'required': True,
#     'description': 'Unique identifier for the investigation.',
#     'ontology_term': 'PPEO:hasIdentifier',
#     'constraints': {'pattern': '^[A-Za-z0-9_-]+$', 'min_length': 1, 'max_length': 100}
# }
```

#### `help()`

Print formatted help showing all fields.

```python
m.Investigation.help()
# ============================================================
# Investigation (miappe v1.1)
# ============================================================
#
# A MIAPPE investigation represents a phenotyping project...
#
# --- Required Fields (2) ---
#   * unique_id: string
#   * title: string
# ...
```

#### `example()`

Generate example code for creating the entity.

```python
m.Investigation.example()
# # Create a Investigation
# Investigation = profile.Investigation
#
# instance = Investigation.create(
#     unique_id="...",
#     title="..."
# )
```

### Creating Entities

#### `create(**kwargs) -> BaseModel`

Create an entity instance with validated data.

```python
import datetime

investigation = m.Investigation.create(
    unique_id="INV-001",
    title="Drought Stress Study",
    description="Investigating drought response in wheat",
    submission_date=datetime.date(2024, 1, 15),
)
```

#### Callable Shorthand

Call the helper directly as a shorthand for `create()`.

```python
# These are equivalent
investigation = m.Investigation.create(unique_id="INV-001", title="My Study")
investigation = m.Investigation(unique_id="INV-001", title="My Study")
```

#### `get_label(instance) -> str`

Get a human-readable label for an entity instance.

```python
inv = m.Investigation(unique_id="INV-001", title="My Study")
label = m.Investigation.get_label(inv)
# "My Study"
```

## Convenience Functions

### `miappe(version: str = "1.1") -> ProfileFacade`

```python
from metaseed import miappe

m = miappe()           # Default version
m = miappe("1.1")      # Explicit version
```

### `isa(version: str = "1.0") -> ProfileFacade`

```python
from metaseed import isa

i = isa()              # Default version
i = isa("1.0")         # Explicit version
```

## Nested Structures

Create complex nested entity structures by composing helpers.

```python
m = miappe()

# Create investigation with nested studies
investigation = m.Investigation(
    unique_id="INV-001",
    title="Complete Phenotyping Project",
    studies=[
        m.Study(
            unique_id="STU-001",
            title="Greenhouse Trial",
        ),
        m.Study(
            unique_id="STU-002",
            title="Field Trial",
        ),
    ],
)

print(len(investigation.studies))  # 2
```

## Discovery Workflow

A typical workflow for exploring an unfamiliar profile:

```python
from metaseed import miappe

# 1. Load the profile
m = miappe()

# 2. See available entities
print(m.entities)

# 3. Get profile overview
m.help()

# 4. Explore a specific entity
m.Investigation.help()

# 5. Check required fields
print(m.Investigation.required_fields)

# 6. Get field details
print(m.Investigation.field_info("unique_id"))

# 7. Find fields by keyword
print(m.search("date"))

# 8. Create an entity
inv = m.Investigation(unique_id="INV-001", title="My Investigation")
```
