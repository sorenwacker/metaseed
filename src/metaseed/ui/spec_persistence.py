"""Abstract persistence interface for spec storage.

This module defines the abstract interface for saving, loading, and managing
user-created specifications. Implementations handle the actual storage mechanism
(filesystem, database, etc.).
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec


class SpecPersistence(ABC):
    """Abstract interface for saving and managing user specs.

    This interface defines the contract for spec persistence operations,
    separating storage concerns from the UI components. Implementations
    may use filesystem, database, or other storage backends.

    The interface distinguishes between user-created specs and built-in
    templates, allowing the UI to present them appropriately.
    """

    @abstractmethod
    async def save(self, spec: "ProfileSpec", name: str | None = None) -> str:
        """Save a spec to persistent storage.

        Args:
            spec: The ProfileSpec to save.
            name: Optional name override. If not provided, uses spec.name.

        Returns:
            The save location or identifier (e.g., file path or database key).

        Raises:
            ValueError: If the spec is invalid or name conflicts with built-in.
            IOError: If the save operation fails.
        """
        pass

    @abstractmethod
    async def delete(self, name: str, version: str | None = None) -> bool:
        """Delete a user-created spec.

        Args:
            name: The spec name to delete.
            version: Optional specific version to delete. If None, deletes all
                versions of the named spec.

        Returns:
            True if the spec was deleted, False if it did not exist.

        Raises:
            ValueError: If attempting to delete a built-in spec.
            IOError: If the delete operation fails.
        """
        pass

    @abstractmethod
    async def list_user_specs(self) -> list[dict]:
        """List all user-created specs.

        Returns:
            List of dictionaries containing spec metadata:
                - name: The spec identifier
                - display_name: Human-readable name
                - versions: List of available version strings
                - description: Brief description of the spec
        """
        pass

    @abstractmethod
    async def list_templates(self) -> list[dict]:
        """List available templates (built-in specs).

        Templates are the built-in specifications that can be cloned
        to create new user specs.

        Returns:
            List of dictionaries containing template metadata:
                - name: The template identifier
                - display_name: Human-readable name
                - versions: List of available version strings
                - description: Brief description of the template
        """
        pass

    @abstractmethod
    async def load_template(self, profile: str, version: str) -> "ProfileSpec":
        """Load a template spec for cloning.

        Args:
            profile: The template profile name.
            version: The specific version to load.

        Returns:
            The loaded ProfileSpec ready for modification.

        Raises:
            FileNotFoundError: If the template does not exist.
            ValueError: If the template cannot be parsed.
        """
        pass

    @abstractmethod
    def is_builtin_name(self, name: str) -> bool:
        """Check if a name conflicts with a built-in spec.

        Used to prevent users from creating specs with names that
        would shadow built-in specifications.

        Args:
            name: The name to check.

        Returns:
            True if the name matches a built-in spec, False otherwise.
        """
        pass
