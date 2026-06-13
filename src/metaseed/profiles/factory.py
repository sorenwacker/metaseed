"""Profile factory for dynamic profile discovery and creation.

This module provides a factory pattern for discovering available profiles
and their versions, and creating ProfileFacade instances.
"""

from __future__ import annotations

from typing import Self

from metaseed.facade import ProfileFacade
from metaseed.specs.loader import SpecLoader


class ProfileFactory:
    """Factory for discovering and creating profile facades.

    Provides dynamic profile discovery using SpecLoader, eliminating
    the need for hardcoded profile lists.

    Example:
        factory = ProfileFactory()
        factory.list_profiles()  # sorted list of available profile names
        factory.list_versions('miappe')  # sorted list of version strings
        facade = factory.create('miappe', '1.1')
    """

    def __init__(self: Self) -> None:
        """Initialize the profile factory."""
        self._loader = SpecLoader()

    def list_profiles(self: Self) -> list[str]:
        """List all available profile names.

        Returns:
            Sorted list of available profile names.
        """
        return self._loader.list_profiles()

    def list_versions(self: Self, profile: str) -> list[str]:
        """List available versions for a profile.

        Args:
            profile: Profile name (e.g., 'miappe', 'isa').

        Returns:
            Sorted list of version strings for the profile.
        """
        loader = SpecLoader(profile=profile)
        return loader.list_versions()

    def get_latest_version(self: Self, profile: str) -> str | None:
        """Get the latest version for a profile.

        Args:
            profile: Profile name.

        Returns:
            Latest version string, or None if no versions found.
        """
        versions = self.list_versions(profile)
        return versions[-1] if versions else None

    def get_profile_info(self: Self) -> list[dict]:
        """Get information about all available profiles.

        Returns:
            List of dictionaries with profile info, each containing
            'name', 'versions', and 'latest' keys.
        """
        profiles = []
        for name in self.list_profiles():
            versions = self.list_versions(name)
            profiles.append(
                {
                    "name": name,
                    "versions": versions,
                    "latest": versions[-1] if versions else None,
                }
            )
        return profiles

    def create(self: Self, profile: str, version: str | None = None) -> ProfileFacade:
        """Create a ProfileFacade for the specified profile and version.

        Args:
            profile: Profile name (e.g., 'miappe', 'isa', 'isa-miappe-combined').
            version: Profile version. If None, uses the latest available.

        Returns:
            ProfileFacade instance for the specified profile.

        Raises:
            ValueError: If profile not found or no versions available.
        """
        if profile not in self.list_profiles():
            raise ValueError(f"Profile not found: {profile}")

        if version is None:
            version = self.get_latest_version(profile)
            if version is None:
                raise ValueError(f"No versions found for profile: {profile}")

        return ProfileFacade(profile, version)

    def get_default_profile(self: Self) -> str:
        """Get the default profile name.

        Returns the first available profile, prioritizing 'miappe' if available.

        Returns:
            Default profile name.

        Raises:
            ValueError: If no profiles are available.
        """
        profiles = self.list_profiles()
        if not profiles:
            raise ValueError("No profiles available")

        # Prefer miappe as default if available
        if "miappe" in profiles:
            return "miappe"

        return profiles[0]
