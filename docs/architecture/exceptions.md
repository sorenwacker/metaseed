# Exception Hierarchy

Metaseed uses two distinct exception hierarchies serving different purposes.

## Overview

| Hierarchy | Base Class | Location | Purpose |
|-----------|------------|----------|---------|
| Internal | `MiappeError` | `core/exceptions.py` | Internal operations, legacy code |
| Public API | `MetaseedError` | `api/errors.py` | Public API boundary |

## When to Use Which

### Use `MetaseedError` (api/errors.py) when:

- Writing code in the public API layer (`api/` module)
- Raising errors that API consumers will catch
- Creating user-facing error messages
- Adding new exception types for the `MetaseedClient` interface

### Use `MiappeError` (core/exceptions.py) when:

- Writing code in internal modules (`core/`, `models/`, `specs/`, `storage/`)
- Raising errors during spec loading, model generation, or validation
- Working with legacy code that already uses this hierarchy

## Exception Flow

Internal exceptions are caught at the API boundary and re-raised as public exceptions:

```
Internal Layer                    Public API Layer
─────────────────                 ─────────────────
SpecError          ──────────>    ProfileNotFoundError
ModelError         ──────────>    EntityTypeNotFoundError
ValidationFailedError ────────>   ValidationError
StorageIOError     ──────────>    (logged, re-raised as appropriate)
```

## Internal Exceptions (MiappeError)

```python
from metaseed.core.exceptions import SpecError, ModelError

# Raised when YAML spec is invalid
raise SpecError("Invalid field type 'unknown' in Investigation.title")

# Raised when model generation fails
raise ModelError("Circular dependency in entity definitions")
```

| Exception | When Raised |
|-----------|-------------|
| `SpecError` | Loading, parsing, or validating YAML specifications |
| `ModelError` | Generating, registering, or accessing Pydantic models |
| `ValidationFailedError` | Entity data fails validation rules |
| `StorageIOError` | File I/O errors during read/write operations |

## Public API Exceptions (MetaseedError)

```python
from metaseed.api.errors import ProfileNotFoundError, ValidationError

try:
    client = MetaseedClient("nonexistent", "1.0")
except ProfileNotFoundError as e:
    print(f"Profile not found: {e.profile}")
```

| Exception | When Raised |
|-----------|-------------|
| `ProfileNotFoundError` | Profile or version does not exist |
| `EntityNotFoundError` | Entity ID not found in store |
| `EntityTypeNotFoundError` | Entity type not in profile schema |
| `ValidationError` | Entity data fails validation |

## Adding New Exceptions

1. Determine the layer: internal operation or public API?
2. Add to the appropriate module
3. Inherit from the correct base class
4. Include structured attributes (not just message strings)
5. Document the exception in this file

Example for public API:

```python
class DatasetNotFoundError(MetaseedError):
    """Dataset not found in storage."""

    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"Dataset '{dataset_id}' not found")
```

Example for internal use:

```python
class SchemaVersionError(MiappeError):
    """Exception raised for schema version conflicts."""
```
