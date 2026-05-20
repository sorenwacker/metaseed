"""Abstract repository interface for dataset storage.

This module defines the abstract interface for dataset CRUD operations,
following the same DI pattern as EntityRepository. Implementations handle
the actual storage mechanism (filesystem, database, etc.).

A dataset is a named collection of entities with metadata about the
profile, version, and modification time.

Two interfaces are provided:
- DatasetRepository: Synchronous interface (for filesystem, simple use cases)
- AsyncDatasetRepository: Asynchronous interface (for database backends)
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DatasetInfo:
    """Summary information about a dataset.

    Used for listing datasets without loading full entity data.
    """

    name: str
    profile: str
    version: str
    entity_count: int
    modified: str


@dataclass
class DatasetData:
    """Full dataset contents including entities.

    This is the transfer object for saving and loading datasets.
    """

    name: str
    profile: str
    version: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    modified: str = ""


def validate_dataset_name(name: str) -> str | None:
    """Validate a dataset name.

    Args:
        name: Dataset name to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Dataset name is required"
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
        return "Name must start with alphanumeric and contain only letters, numbers, hyphens, underscores"
    if len(name) > 64:
        return "Name must be 64 characters or less"
    return None


class DatasetRepository(ABC):
    """Abstract interface for synchronous dataset persistence.

    This interface defines the contract for dataset CRUD operations,
    separating storage concerns from business logic. Implementations
    may use filesystem or other synchronous backends.

    For async backends (databases), use AsyncDatasetRepository instead.
    """

    @abstractmethod
    def list(self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries, sorted by modified time (most recent first).
        """
        pass

    @abstractmethod
    def save(self, name: str, data: DatasetData) -> DatasetInfo:
        """Save a dataset.

        Args:
            name: Dataset name (must be valid per validate_name).
            data: Dataset contents to save.

        Returns:
            DatasetInfo for the saved dataset.

        Raises:
            ValueError: If name is invalid.
        """
        pass

    @abstractmethod
    def load(self, name: str) -> DatasetData:
        """Load a dataset by name.

        Args:
            name: Dataset name to load.

        Returns:
            DatasetData with full contents.

        Raises:
            FileNotFoundError: If dataset doesn't exist.
        """
        pass

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Delete a dataset.

        Args:
            name: Dataset name to delete.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Check if a dataset exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        pass

    @staticmethod
    def validate_name(name: str) -> str | None:
        """Validate a dataset name."""
        return validate_dataset_name(name)


class AsyncDatasetRepository(ABC):
    """Abstract interface for asynchronous dataset persistence.

    This interface defines the contract for async dataset CRUD operations,
    suitable for database backends using async SQLAlchemy or similar.

    For sync backends (filesystem), use DatasetRepository instead.
    """

    @abstractmethod
    async def list(self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries, sorted by modified time (most recent first).
        """
        pass

    @abstractmethod
    async def save(self, name: str, data: DatasetData) -> DatasetInfo:
        """Save a dataset.

        Args:
            name: Dataset name (must be valid per validate_name).
            data: Dataset contents to save.

        Returns:
            DatasetInfo for the saved dataset.

        Raises:
            ValueError: If name is invalid.
        """
        pass

    @abstractmethod
    async def load(self, name: str) -> DatasetData:
        """Load a dataset by name.

        Args:
            name: Dataset name to load.

        Returns:
            DatasetData with full contents.

        Raises:
            FileNotFoundError: If dataset doesn't exist.
        """
        pass

    @abstractmethod
    async def delete(self, name: str) -> bool:
        """Delete a dataset.

        Args:
            name: Dataset name to delete.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    async def exists(self, name: str) -> bool:
        """Check if a dataset exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        pass

    @staticmethod
    def validate_name(name: str) -> str | None:
        """Validate a dataset name."""
        return validate_dataset_name(name)
