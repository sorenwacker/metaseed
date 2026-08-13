# Exceptions

Metaseed has one exception hierarchy, at the public API boundary, plus module-local exceptions that never cross it.

## Public API hierarchy (`api/errors.py`)

Everything a consumer of `MetaseedClient` can catch inherits from `MetaseedError`.

```python
from metaseed.api.errors import ProfileNotFoundError, ValidationError

try:
    client = MetaseedClient("nonexistent", "1.0")
except ProfileNotFoundError as e:
    print(f"Profile not found: {e.profile}")
```

| Exception | When raised |
|-----------|-------------|
| `ProfileNotFoundError` | Profile or version does not exist |
| `InvalidSpecError` | A specification cannot be parsed or is inconsistent |
| `EntityNotFoundError` | Entity ID not found in the store |
| `EntityTypeNotFoundError` | Entity type not in the profile schema |
| `ValidationError` | Entity data fails validation |

## Module-local exceptions

Modules below the API raise their own exceptions and the API layer translates them at its boundary. These are implementation details: code outside the raising module's layer catches the public exception, not these.

| Exception | Module | When raised |
|-----------|--------|-------------|
| `SpecLoadError` | `specs/loader.py` | Loading or parsing a YAML specification |
| `SeekApiError` | `seek/client.py` | A SEEK instance answers with an error status |
| `OntologyServiceError` | `services/ontology.py` | An ontology lookup fails |

## Adding an exception

1. If API consumers must catch it, add it to `api/errors.py` inheriting `MetaseedError`; otherwise define it in the module that raises it.
2. Carry structured attributes, not just a message string.

```python
class DatasetNotFoundError(MetaseedError):
    """Dataset not found in storage."""

    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"Dataset '{dataset_id}' not found")
```
