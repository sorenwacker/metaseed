"""Base classes for storage backends.

This module defines the storage backend interface and common error types.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Self, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class StorageError(Exception):
    """Raised when a storage operation fails."""


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    Defines the interface for saving and loading Pydantic models
    to different file formats.
    """

    @abstractmethod
    def save(self: Self, entity: BaseModel, path: Path) -> None:
        """Save an entity to a file.

        Args:
            entity: Pydantic model instance to save.
            path: Path where to save the file.

        Raises:
            StorageError: If the save operation fails.
        """
        ...

    @abstractmethod
    def load(self: Self, path: Path, model: type[T]) -> T:
        """Load an entity from a file.

        Args:
            path: Path to the file to load.
            model: Pydantic model class to instantiate.

        Returns:
            Loaded model instance.

        Raises:
            StorageError: If the load operation fails.
        """
        ...
