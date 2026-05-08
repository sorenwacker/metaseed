# Storage Backends

Storage backends handle persisting Pydantic models to files and loading them back.

## Overview

The storage module provides a unified interface for saving and loading metadata entities to different file formats. Each backend serializes Pydantic models while preserving type information through the model's schema.

## Quick Start

```python
from pathlib import Path
from metaseed.storage.json_backend import JsonStorage
from metaseed.storage.yaml_backend import YamlStorage
from metaseed.models.registry import get_model

# Get a model from the registry
Study = get_model("Study", profile="miappe", version="1.1")

# Create an instance
study = Study(
    unique_id="STUDY001",
    title="Example Study",
    start_date="2024-03-01"
)

# Save as JSON
json_storage = JsonStorage()
json_storage.save(study, Path("data/study.json"))

# Save as YAML
yaml_storage = YamlStorage()
yaml_storage.save(study, Path("data/study.yaml"))

# Load back
loaded = json_storage.load(Path("data/study.json"), Study)
```

## StorageBackend Interface

All backends implement the `StorageBackend` abstract base class:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel

class StorageBackend(ABC):
    @abstractmethod
    def save(self, entity: BaseModel, path: Path) -> None:
        """Save an entity to a file."""
        ...

    @abstractmethod
    def load(self, path: Path, model: type[T]) -> T:
        """Load an entity from a file."""
        ...
```

## JSON Backend

`JsonStorage` saves entities as formatted JSON files.

```python
from metaseed.storage.json_backend import JsonStorage

# Pretty-printed with 2-space indent (default)
storage = JsonStorage()

# Compact output
storage = JsonStorage(indent=None)

# Custom indent
storage = JsonStorage(indent=4)
```

### Output Format

```json
{
  "unique_id": "STUDY001",
  "title": "Example Study",
  "start_date": "2024-03-01"
}
```

Features:

- Creates parent directories automatically
- Excludes `None` values from output
- UTF-8 encoding

## YAML Backend

`YamlStorage` saves entities as YAML files, preferred for human-edited metadata.

```python
from metaseed.storage.yaml_backend import YamlStorage

storage = YamlStorage()
storage.save(study, Path("data/study.yaml"))
```

### Output Format

```yaml
unique_id: STUDY001
title: Example Study
start_date: '2024-03-01'
```

Features:

- Creates parent directories automatically
- Excludes `None` values from output
- Preserves key order
- Supports Unicode characters
- Uses block style (not flow style) for readability

## Error Handling

Both backends raise `StorageError` for failures:

```python
from metaseed.storage.base import StorageError

try:
    study = storage.load(Path("missing.json"), Study)
except StorageError as e:
    print(f"Load failed: {e}")
```

| Error Condition | Message |
|-----------------|---------|
| File not found | `File not found: {path}` |
| Invalid JSON | `Invalid JSON in {path}: {details}` |
| Invalid YAML | `Invalid YAML in {path}: {details}` |
| Schema mismatch | `Data in {path} doesn't match model: {details}` |
| Write failure | `Failed to save to {path}: {details}` |
| Read failure | `Failed to read {path}: {details}` |

## Loading with Validation

When loading, the backend validates data against the Pydantic model:

```python
from pydantic import ValidationError
from metaseed.storage.base import StorageError

try:
    study = storage.load(Path("data/study.json"), Study)
except StorageError as e:
    # StorageError wraps Pydantic ValidationError
    print(f"Invalid data: {e}")
```

If the file contains data that does not match the model schema (missing required fields, wrong types), a `StorageError` is raised with validation details.

## Custom Backends

Create custom backends by subclassing `StorageBackend`:

```python
from metaseed.storage.base import StorageBackend, StorageError
from pathlib import Path
from pydantic import BaseModel
import toml

class TomlStorage(StorageBackend):
    """TOML file storage backend."""

    def save(self, entity: BaseModel, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = entity.model_dump(mode="json", exclude_none=True)
            path.write_text(toml.dumps(data), encoding="utf-8")
        except OSError as e:
            raise StorageError(f"Failed to save to {path}: {e}") from e

    def load(self, path: Path, model: type[T]) -> T:
        if not path.exists():
            raise StorageError(f"File not found: {path}")
        try:
            data = toml.loads(path.read_text(encoding="utf-8"))
            return model.model_validate(data)
        except Exception as e:
            raise StorageError(f"Failed to load {path}: {e}") from e
```

## Choosing a Format

| Format | Best For |
|--------|----------|
| JSON | Machine processing, APIs, interoperability |
| YAML | Human editing, configuration, metadata files |

Both formats round-trip cleanly through Pydantic models.

## See Also

- [Schema Specs](schema-specs.md) - Defining entity schemas
- [Model Factory](../architecture/model-factory.md) - How specs become Pydantic models
