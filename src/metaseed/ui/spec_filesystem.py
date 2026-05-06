"""Filesystem implementations of spec persistence and provider interfaces.

This module provides concrete implementations of SpecPersistence and SpecProvider
that use the local filesystem for storage, leveraging existing logic from
spec_builder_helpers.py and SpecLoader.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from metaseed.specs.loader import SpecLoader
from metaseed.ui.spec_persistence import SpecPersistence
from metaseed.ui.spec_provider import SpecProvider

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec


class FilesystemSpecPersistence(SpecPersistence):
    """Filesystem-based implementation of spec persistence.

    Uses the user specs directory (~/.local/share/metaseed/specs/) for storing
    user-created specifications. Built-in specs are read-only and loaded
    via SpecLoader.
    """

    def __init__(self) -> None:
        """Initialize the filesystem persistence layer."""
        self._loader = SpecLoader()

    async def save(self, spec: ProfileSpec, name: str | None = None) -> str:
        """Save a spec to the filesystem.

        Saves to specs/<name>/<version>/profile.yaml structure in the user
        specs directory.

        Args:
            spec: The ProfileSpec to save.
            name: Optional name override. If not provided, uses spec.name.

        Returns:
            The file path where the spec was saved.

        Raises:
            ValueError: If the name is empty or conflicts with a built-in spec.
        """
        from metaseed.ui.spec_builder_helpers import save_spec

        path = save_spec(spec, name)
        return str(path)

    async def delete(self, name: str, version: str | None = None) -> bool:
        """Delete a user-created spec from the filesystem.

        Args:
            name: The spec name to delete.
            version: Optional specific version to delete. If None, deletes all
                versions of the named spec.

        Returns:
            True if the spec was deleted, False if it did not exist.

        Raises:
            ValueError: If attempting to delete a built-in spec.
        """
        from metaseed.ui.spec_builder_helpers import delete_user_spec

        return delete_user_spec(name, version)

    async def list_user_specs(self) -> list[dict]:
        """List all user-created specs from the filesystem.

        Returns:
            List of dictionaries containing spec metadata:
                - name: The spec identifier
                - display_name: Human-readable name
                - versions: List of available version strings
                - description: Brief description of the spec
        """
        from metaseed.ui.spec_builder_helpers import list_user_specs

        return list_user_specs()

    async def list_templates(self) -> list[dict]:
        """List available built-in templates from the filesystem.

        Returns:
            List of dictionaries containing template metadata:
                - name: The template identifier
                - display_name: Human-readable name
                - versions: List of available version strings
                - description: Brief description of the template
        """
        from metaseed.ui.spec_builder_helpers import list_available_templates

        return list_available_templates()

    async def load_template(self, profile: str, version: str) -> ProfileSpec:
        """Load a template spec for cloning.

        Args:
            profile: The template profile name.
            version: The specific version to load.

        Returns:
            A deep copy of the ProfileSpec ready for modification.

        Raises:
            FileNotFoundError: If the template does not exist.
            ValueError: If the template cannot be parsed.
        """
        from metaseed.specs.loader import SpecLoadError

        try:
            spec = self._loader.load_profile(version=version, profile=profile)
            return copy.deepcopy(spec)
        except SpecLoadError as e:
            raise FileNotFoundError(str(e)) from e

    def is_builtin_name(self, name: str) -> bool:
        """Check if a name conflicts with a built-in spec.

        Args:
            name: The name to check.

        Returns:
            True if the name matches a built-in spec, False otherwise.
        """
        safe_name = name.lower().strip()
        builtin_profiles = [
            p.lower() for p in self._loader.list_profiles() if not self._loader.is_user_defined(p)
        ]
        return safe_name in builtin_profiles


class FilesystemSpecProvider(SpecProvider):
    """Filesystem-based implementation of spec provider.

    Provides read-only access to specifications using SpecLoader. Combines
    built-in and user-defined specs into a unified interface.
    """

    def __init__(self) -> None:
        """Initialize the filesystem provider."""
        self._loader = SpecLoader()

    async def list_profiles(self) -> list[str]:
        """List all available profile names from the filesystem.

        Returns:
            List of profile name strings, sorted alphabetically.
        """
        return self._loader.list_profiles()

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
        versions = self._loader.list_versions(profile)
        if not versions:
            raise FileNotFoundError(f"Profile not found: {profile}")
        # Return in descending order (newest first)
        return sorted(versions, reverse=True)

    async def get_spec(self, profile: str, version: str) -> ProfileSpec:
        """Load a specific spec from the filesystem.

        Args:
            profile: The profile name.
            version: The version string.

        Returns:
            The loaded ProfileSpec.

        Raises:
            FileNotFoundError: If the spec does not exist.
            ValueError: If the spec cannot be parsed.
        """
        from metaseed.specs.loader import SpecLoadError

        try:
            return self._loader.load_profile(version=version, profile=profile)
        except SpecLoadError as e:
            raise FileNotFoundError(str(e)) from e

    async def get_display_name(self, profile: str) -> str:
        """Get the display name for a profile.

        Loads the latest version of the profile and returns its display_name.
        Falls back to the profile name if no display name is defined.

        Args:
            profile: The profile name.

        Returns:
            The human-readable display name.

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        versions = self._loader.list_versions(profile)
        if not versions:
            raise FileNotFoundError(f"Profile not found: {profile}")

        # Load the latest version to get display name
        latest_version = sorted(versions)[-1]
        try:
            spec = self._loader.load_profile(version=latest_version, profile=profile)
            return spec.display_name or profile
        except Exception:
            return profile
