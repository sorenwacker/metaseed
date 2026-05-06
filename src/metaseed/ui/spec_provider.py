"""Abstract provider interface for spec data access.

This module defines the abstract interface for accessing specification data.
Used by Explorer and comparison components to retrieve spec information
without coupling to specific storage implementations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec


class SpecProvider(ABC):
    """Abstract interface for accessing specs.

    This interface provides read-only access to specifications for
    Explorer and comparison features. It abstracts the underlying
    storage mechanism (filesystem, database, etc.) from the UI components.

    Implementations may combine multiple sources (built-in specs,
    user specs) into a unified interface.
    """

    @abstractmethod
    async def list_profiles(self) -> list[str]:
        """List all available profile names.

        Returns:
            List of profile name strings, sorted alphabetically.
        """
        pass

    @abstractmethod
    async def list_versions(self, profile: str) -> list[str]:
        """List available versions for a profile.

        Args:
            profile: The profile name to query.

        Returns:
            List of version strings, sorted in descending order
            (newest first).

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        pass

    @abstractmethod
    async def get_spec(self, profile: str, version: str) -> "ProfileSpec":
        """Load a specific spec.

        Args:
            profile: The profile name.
            version: The version string.

        Returns:
            The loaded ProfileSpec.

        Raises:
            FileNotFoundError: If the spec does not exist.
            ValueError: If the spec cannot be parsed.
        """
        pass

    @abstractmethod
    async def get_display_name(self, profile: str) -> str:
        """Get the display name for a profile.

        Args:
            profile: The profile name.

        Returns:
            The human-readable display name. Falls back to the
            profile name if no display name is defined.

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        pass
