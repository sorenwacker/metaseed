"""JSON storage backend.

This module provides JSON file storage for MIAPPE entities.
"""

import json
from pathlib import Path
from typing import Self, TypeVar

from pydantic import BaseModel, ValidationError

from miappe_api.storage.base import StorageBackend, StorageError

T = TypeVar("T", bound=BaseModel)


class JsonStorage(StorageBackend):
    """JSON file storage backend.

    Saves and loads Pydantic models as JSON files.

    Attributes:
        indent: Indentation level for pretty-printing. None for compact.
    """

    def __init__(self: Self, indent: int | None = 2) -> None:
        """Initialize the JSON storage backend.

        Args:
            indent: Indentation level for JSON output. Set to None for compact.
        """
        self.indent = indent

    def save(self: Self, entity: BaseModel, path: Path) -> None:
        """Save an entity to a JSON file.

        Creates parent directories if they don't exist.

        Args:
            entity: Pydantic model instance to save.
            path: Path where to save the JSON file.

        Raises:
            StorageError: If the save operation fails.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            json_str = entity.model_dump_json(indent=self.indent, exclude_none=True)
            path.write_text(json_str, encoding="utf-8")
        except OSError as e:
            raise StorageError(f"Failed to save to {path}: {e}") from e

    def load(self: Self, path: Path, model: type[T]) -> T:
        """Load an entity from a JSON file.

        Args:
            path: Path to the JSON file.
            model: Pydantic model class to instantiate.

        Returns:
            Loaded model instance.

        Raises:
            StorageError: If the file doesn't exist, isn't valid JSON,
                or doesn't match the model schema.
        """
        if not path.exists():
            raise StorageError(f"File not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return model.model_validate(data)
        except json.JSONDecodeError as e:
            raise StorageError(f"Invalid JSON in {path}: {e}") from e
        except ValidationError as e:
            raise StorageError(f"Data in {path} doesn't match model: {e}") from e
        except OSError as e:
            raise StorageError(f"Failed to read {path}: {e}") from e
