"""Model registry for caching and retrieving generated models.

This module provides a registry to store and retrieve dynamically generated
Pydantic models, avoiding redundant model generation.
"""

from typing import Self

from pydantic import BaseModel


class ModelNotFoundError(Exception):
    """Raised when a requested model is not found in the registry."""


class ModelRegistry:
    """Registry for storing and retrieving generated models.

    Models are keyed by (name, version) tuples to support multiple
    profile versions.
    """

    def __init__(self: Self) -> None:
        """Initialize an empty registry."""
        self._models: dict[tuple[str, str], type[BaseModel]] = {}

    def register(self: Self, name: str, version: str, model: type[BaseModel]) -> None:
        """Register a model in the registry.

        Args:
            name: Model name (e.g., "Investigation").
            version: Profile version (e.g., "1.1").
            model: Pydantic model class to register.
        """
        self._models[(name, version)] = model

    def get(self: Self, name: str, version: str) -> type[BaseModel]:
        """Retrieve a model from the registry.

        Args:
            name: Model name.
            version: Profile version.

        Returns:
            The registered model class.

        Raises:
            ModelNotFoundError: If the model is not registered.
        """
        key = (name, version)
        if key not in self._models:
            raise ModelNotFoundError(f"Model not found: {name} (version {version})")
        return self._models[key]

    def has(self: Self, name: str, version: str) -> bool:
        """Check if a model is registered.

        Args:
            name: Model name.
            version: Profile version.

        Returns:
            True if the model is registered, False otherwise.
        """
        return (name, version) in self._models

    def list_models(
        self: Self, version: str | None = None
    ) -> list[tuple[str, str]] | list[str]:
        """List registered models.

        Args:
            version: If provided, list only models for this version.

        Returns:
            List of (name, version) tuples, or list of names if version specified.
        """
        if version is not None:
            return [name for (name, ver) in self._models if ver == version]
        return list(self._models.keys())

    def clear(self: Self) -> None:
        """Clear all registered models."""
        self._models.clear()


# Global registry instance
_global_registry = ModelRegistry()


def get_global_registry() -> ModelRegistry:
    """Get the global model registry.

    Returns:
        The global ModelRegistry instance.
    """
    return _global_registry
