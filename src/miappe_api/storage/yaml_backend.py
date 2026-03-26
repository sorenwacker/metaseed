"""YAML storage backend.

This module provides YAML file storage for MIAPPE entities.
"""

from pathlib import Path
from typing import Self, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from miappe_api.storage.base import StorageBackend, StorageError

T = TypeVar("T", bound=BaseModel)


class YamlStorage(StorageBackend):
    """YAML file storage backend.

    Saves and loads Pydantic models as YAML files. YAML is more
    human-readable than JSON and is the preferred format for
    configuration and metadata files.
    """

    def save(self: Self, entity: BaseModel, path: Path) -> None:
        """Save an entity to a YAML file.

        Creates parent directories if they don't exist.

        Args:
            entity: Pydantic model instance to save.
            path: Path where to save the YAML file.

        Raises:
            StorageError: If the save operation fails.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = entity.model_dump(exclude_none=True)
            yaml_str = yaml.dump(
                data,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            path.write_text(yaml_str, encoding="utf-8")
        except OSError as e:
            raise StorageError(f"Failed to save to {path}: {e}") from e

    def load(self: Self, path: Path, model: type[T]) -> T:
        """Load an entity from a YAML file.

        Args:
            path: Path to the YAML file.
            model: Pydantic model class to instantiate.

        Returns:
            Loaded model instance.

        Raises:
            StorageError: If the file doesn't exist, isn't valid YAML,
                or doesn't match the model schema.
        """
        if not path.exists():
            raise StorageError(f"File not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if data is None:
                data = {}
            return model.model_validate(data)
        except yaml.YAMLError as e:
            raise StorageError(f"Invalid YAML in {path}: {e}") from e
        except ValidationError as e:
            raise StorageError(f"Data in {path} doesn't match model: {e}") from e
        except OSError as e:
            raise StorageError(f"Failed to read {path}: {e}") from e
