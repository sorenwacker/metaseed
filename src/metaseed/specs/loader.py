"""Spec loader for profile YAML specifications.

This module provides functionality to load and parse YAML specification files
that define entities and their fields for various profiles (MIAPPE, ISA, etc.).

Directory structure:
    specs/
        <profile-name>/
            <version>/
                profile.yaml
"""

from pathlib import Path
from typing import Self

import yaml
from pydantic import ValidationError

from metaseed.specs.schema import EntitySpec, ProfileSpec


class SpecLoadError(Exception):
    """Raised when a specification file cannot be loaded or parsed."""


class SpecLoader:
    """Loader for profile YAML specifications.

    Supports multiple profiles organized in directories:
        specs/<profile>/<version>/profile.yaml

    Example:
        specs/miappe/1.1/profile.yaml
        specs/darwin-core/1.0/profile.yaml
    """

    def __init__(self: Self, profile: str = "miappe") -> None:
        """Initialize the spec loader.

        Args:
            profile: Profile name (e.g., "miappe", "isa"). Defaults to "miappe".
        """
        self._specs_dir = Path(__file__).parent
        self._profile_cache: dict[str, ProfileSpec] = {}
        self._default_profile = profile.lower()

    def _find_profile_file(self: Self, version: str, profile: str | None = None) -> Path | None:
        """Find profile file for a version.

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            Path to profile file or None if not found.
        """
        profile = (profile or self._default_profile).lower()

        # New structure: specs/<profile>/<version>/profile.yaml
        profile_path = self._specs_dir / profile / version / "profile.yaml"
        if profile_path.exists():
            return profile_path

        return None

    def _cache_key(self: Self, version: str, profile: str | None = None) -> str:
        """Generate cache key for profile+version combination."""
        profile = (profile or self._default_profile).lower()
        return f"{profile}:{version}"

    def _load_profile(self: Self, version: str, profile: str | None = None) -> ProfileSpec | None:
        """Load unified profile spec for a version.

        Args:
            version: Version string.
            profile: Profile name. Uses default if None.

        Returns:
            ProfileSpec or None if no unified profile exists.
        """
        cache_key = self._cache_key(version, profile)
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        profile_path = self._find_profile_file(version, profile)
        if profile_path is None:
            return None

        try:
            content = profile_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if data is None:
                return None
            loaded_profile = ProfileSpec.model_validate(data)
            self._profile_cache[cache_key] = loaded_profile
            return loaded_profile
        except (yaml.YAMLError, ValidationError):
            return None

    def load(self: Self, path: Path) -> EntitySpec:
        """Load an entity spec from a YAML file.

        Args:
            path: Path to the YAML specification file.

        Returns:
            Parsed EntitySpec object.

        Raises:
            SpecLoadError: If the file cannot be read or parsed.
        """
        if not path.exists():
            raise SpecLoadError(f"Specification file not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            return self.load_from_string(content)
        except yaml.YAMLError as e:
            raise SpecLoadError(f"Failed to parse YAML: {e}") from e

    def load_from_string(self: Self, yaml_str: str) -> EntitySpec:
        """Load an entity spec from a YAML string.

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Parsed EntitySpec object.

        Raises:
            SpecLoadError: If the YAML is invalid or doesn't match schema.
        """
        try:
            data = yaml.safe_load(yaml_str)
            if data is None:
                raise SpecLoadError("Empty YAML content")
            return EntitySpec.model_validate(data)
        except yaml.YAMLError as e:
            raise SpecLoadError(f"Failed to parse YAML: {e}") from e
        except ValidationError as e:
            errors = e.errors()
            if errors:
                first_error = errors[0]
                loc = ".".join(str(part) for part in first_error["loc"])
                msg = first_error["msg"]
                raise SpecLoadError(f"Invalid specification at {loc}: {msg}") from e
            raise SpecLoadError(f"Invalid specification: {e}") from e

    def load_profile(self: Self, version: str = "1.1", profile: str | None = None) -> ProfileSpec:
        """Load a unified profile spec.

        Args:
            version: Profile version (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            ProfileSpec object.

        Raises:
            SpecLoadError: If profile not found.
        """
        profile_name = profile or self._default_profile
        loaded = self._load_profile(version, profile)
        if loaded is None:
            raise SpecLoadError(f"Profile not found: {profile_name} version {version}")
        return loaded

    def load_entity(
        self: Self, entity: str, version: str = "1.1", profile: str | None = None
    ) -> EntitySpec:
        """Load an entity spec by name and version.

        Args:
            entity: Entity name (e.g., "investigation" or "Investigation").
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            Parsed EntitySpec object.

        Raises:
            SpecLoadError: If the entity or version is not found.
        """
        profile_name = profile or self._default_profile

        loaded_profile = self._load_profile(version, profile)
        if loaded_profile is not None:
            try:
                return loaded_profile.get_entity(entity)
            except KeyError:
                raise SpecLoadError(
                    f"Entity not found: {entity} ({profile_name} v{version})"
                ) from None

        raise SpecLoadError(f"Profile not found: {profile_name} v{version}")

    def list_entities(self: Self, version: str = "1.1", profile: str | None = None) -> list[str]:
        """List available entities for a version.

        Returns entities in the order defined in the profile YAML, which is
        typically hierarchical (Investigation → Study → nested entities).

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            List of entity names in definition order.

        Raises:
            SpecLoadError: If the version is not found.
        """
        profile_name = profile or self._default_profile

        loaded_profile = self._load_profile(version, profile)
        if loaded_profile is not None:
            return loaded_profile.list_entities()

        raise SpecLoadError(f"Version not found: {profile_name} v{version}")

    def list_versions(self: Self, profile: str | None = None) -> list[str]:
        """List available versions for a profile.

        Args:
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            List of version strings (e.g., ["1.1"]).
        """
        profile_name = (profile or self._default_profile).lower()
        versions = []

        # Look for version directories under profile folder
        profile_dir = self._specs_dir / profile_name
        if profile_dir.exists() and profile_dir.is_dir():
            for version_dir in sorted(profile_dir.iterdir()):
                if version_dir.is_dir() and (version_dir / "profile.yaml").exists():
                    versions.append(version_dir.name)

        return versions

    def list_profiles(self: Self) -> list[str]:
        """List available profiles.

        Returns:
            List of profile names (e.g., ["miappe", "isa", "darwin-core"]).
        """
        profiles = []

        # Find all directories that contain at least one version with profile.yaml
        for item in sorted(self._specs_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("_"):
                # Check if any subdirectory has a profile.yaml
                for version_dir in item.iterdir():
                    if version_dir.is_dir() and (version_dir / "profile.yaml").exists():
                        profiles.append(item.name)
                        break

        return profiles

    def get_profile_path(
        self: Self, version: str = "1.1", profile: str | None = None
    ) -> Path | None:
        """Get path to the profile YAML file.

        Args:
            version: Version string.
            profile: Profile name. Uses default if None.

        Returns:
            Path to profile file or None.
        """
        return self._find_profile_file(version, profile)
