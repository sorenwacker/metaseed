"""Filesystem implementation of DatasetRepository.

Stores datasets as JSON files in a configurable directory.
This is the default implementation used by metaseed standalone.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from metaseed.paths import user_data_base
from metaseed.repositories.dataset_repository import (
    CatalogMetadata,
    DatasetData,
    DatasetInfo,
    DatasetRepository,
)

DEFAULT_DATASETS_DIR = user_data_base() / "datasets"
"""Where datasets live when nothing overrides it.

Derived from the same base as every other metaseed data directory, so
``XDG_DATA_HOME`` (and ``%LOCALAPPDATA%`` on Windows) is honoured here as it
is for specs. It was hardcoded to ``~/.local/share`` in two places, which
meant a redirected data directory silently kept datasets in the real one.
"""

#: Environment variable overriding where datasets are stored. Lets tests (and
#: sandboxed deployments) point storage at a throwaway directory instead of the
#: user's real data dir — the selenium suite uses it for hermetic isolation.
DATASETS_DIR_ENV = "METASEED_DATASETS_DIR"


def default_datasets_dir() -> Path:
    """The datasets directory, honoring the ``METASEED_DATASETS_DIR`` override.

    Falls back to :data:`DEFAULT_DATASETS_DIR` (read at call time, so tests that
    patch it still take effect).
    """
    override = os.environ.get(DATASETS_DIR_ENV)
    if override:
        return Path(override)
    return DEFAULT_DATASETS_DIR


class FilesystemDatasetRepository(DatasetRepository):
    """Filesystem-based dataset storage.

    Stores each dataset as a JSON file in the configured directory.
    File name is {dataset_name}.json.
    """

    def __init__(self, datasets_dir: Path | None = None):
        """Initialize filesystem repository.

        Args:
            datasets_dir: Directory for dataset files. Defaults to
                ``$METASEED_DATASETS_DIR`` or ~/.local/share/metaseed/datasets.
        """
        self._dir = datasets_dir or default_datasets_dir()
        self._ensure_dir()

    def _ensure_dir(self: Self) -> None:
        """Ensure the datasets directory exists."""
        self._dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self: Self, name: str) -> Path:
        """Resolve the on-disk path for a dataset, rejecting unsafe names.

        The name is interpolated straight into a filename, so a value like
        ``../../etc/passwd`` or an absolute path would escape the datasets
        directory. This is the single choke point shared by save/load/delete/
        exists, so validating here protects every operation rather than only
        the save path.

        Raises:
            ValueError: If the name is not a valid dataset name.
        """
        error = self.validate_name(name)
        if error:
            raise ValueError(error)
        return self._dir / f"{name}.json"

    def list(self: Self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries, sorted by modified time (most recent first).
        """
        self._ensure_dir()
        datasets = []

        for path in sorted(self._dir.glob("*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)

                entity_count = len(data.get("entities", []))

                datasets.append(
                    DatasetInfo(
                        name=path.stem,
                        profile=data.get("profile", "unknown"),
                        version=data.get("version", "unknown"),
                        entity_count=entity_count,
                        modified=data.get("modified", str(path.stat().st_mtime)),
                    )
                )
            except (json.JSONDecodeError, OSError):
                continue

        datasets.sort(key=lambda d: d.modified, reverse=True)
        return datasets

    def save(self: Self, name: str, data: DatasetData) -> DatasetInfo:
        """Save a dataset to a JSON file.

        Args:
            name: Dataset name.
            data: Dataset contents to save.

        Returns:
            DatasetInfo for the saved dataset.

        Raises:
            ValueError: If name is invalid.
        """
        error = self.validate_name(name)
        if error:
            raise ValueError(error)

        self._ensure_dir()
        path = self._get_path(name)

        modified = data.modified or datetime.now(UTC).isoformat()

        file_data: dict[str, Any] = {
            "name": name,
            "profile": data.profile,
            "version": data.version,
            "entities": data.entities,
            "modified": modified,
        }
        if data.catalog_metadata is not None:
            file_data["catalog_metadata"] = asdict(data.catalog_metadata)

        with open(path, "w") as f:
            json.dump(file_data, f, indent=2, default=str)

        return DatasetInfo(
            name=name,
            profile=data.profile,
            version=data.version,
            entity_count=len(data.entities),
            modified=modified,
        )

    def load(self: Self, name: str) -> DatasetData:
        """Load a dataset from a JSON file.

        Args:
            name: Dataset name to load.

        Returns:
            DatasetData with full contents.

        Raises:
            FileNotFoundError: If dataset doesn't exist.
        """
        path = self._get_path(name)

        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {name}")

        with open(path) as f:
            data = json.load(f)

        catalog_metadata = data.get("catalog_metadata")
        return DatasetData(
            name=data.get("name", name),
            profile=data.get("profile", "unknown"),
            version=data.get("version", "unknown"),
            entities=data.get("entities", []),
            modified=data.get("modified", ""),
            catalog_metadata=(
                CatalogMetadata(**catalog_metadata) if catalog_metadata else None
            ),
        )

    def delete(self: Self, name: str) -> bool:
        """Delete a dataset file.

        Args:
            name: Dataset name to delete.

        Returns:
            True if deleted, False if not found.
        """
        path = self._get_path(name)

        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self: Self, name: str) -> bool:
        """Check if a dataset file exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        return self._get_path(name).exists()
