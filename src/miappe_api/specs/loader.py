"""Spec loader for profile YAML specifications.

This module provides functionality to load and parse YAML specification files
that define entities and their fields for various profiles (MIAPPE, ISA, etc.).
"""

import re
from pathlib import Path
from typing import Self

import yaml
from pydantic import ValidationError

from miappe_api.specs.schema import EntitySpec, ProfileSpec


class SpecLoadError(Exception):
    """Raised when a specification file cannot be loaded or parsed."""


class SpecLoader:
    """Loader for profile YAML specifications.

    Supports multiple profiles (MIAPPE, ISA, etc.) with unified YAML files.
    Each profile is defined in a single YAML file (e.g., miappe_v1.1.yaml, isa_v1.0.yaml).
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
        """Find unified profile file for a version.

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            Path to profile file or None if not found.
        """
        profile = (profile or self._default_profile).lower()

        # Try different naming patterns
        patterns = [
            f"{profile}_v{version}.yaml",
            f"{profile}_{version}.yaml",
        ]
        for pattern in patterns:
            path = self._specs_dir / pattern
            if path.exists():
                return path
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

        First tries unified profile, then falls back to individual files.

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

        # Try unified profile first
        loaded_profile = self._load_profile(version, profile)
        if loaded_profile is not None:
            try:
                return loaded_profile.get_entity(entity)
            except KeyError:
                raise SpecLoadError(
                    f"Entity not found: {entity} ({profile_name} v{version})"
                ) from None

        # Fall back to individual files (only for default MIAPPE profile)
        if profile_name == "miappe":
            version_dir = self._specs_dir / f"v{version.replace('.', '_')}"
            if not version_dir.exists():
                raise SpecLoadError(f"Version not found: {profile_name} v{version}")

            # Convert CamelCase to snake_case for file lookup
            entity_snake = re.sub(r"(?<!^)(?=[A-Z])", "_", entity).lower()
            spec_file = version_dir / f"{entity_snake}.yaml"
            if not spec_file.exists():
                # Try original name
                spec_file = version_dir / f"{entity.lower()}.yaml"
                if not spec_file.exists():
                    raise SpecLoadError(f"Entity not found: {entity} ({profile_name} v{version})")

            return self.load(spec_file)

        raise SpecLoadError(f"Profile not found: {profile_name} v{version}")

    def list_entities(self: Self, version: str = "1.1", profile: str | None = None) -> list[str]:
        """List available entities for a version.

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            List of entity names.

        Raises:
            SpecLoadError: If the version is not found.
        """
        profile_name = profile or self._default_profile

        # Try unified profile first
        loaded_profile = self._load_profile(version, profile)
        if loaded_profile is not None:
            return sorted(loaded_profile.list_entities())

        # Fall back to individual files (only for default MIAPPE profile)
        if profile_name == "miappe":
            version_dir = self._specs_dir / f"v{version.replace('.', '_')}"
            if not version_dir.exists():
                raise SpecLoadError(f"Version not found: {profile_name} v{version}")

            return sorted(f.stem for f in version_dir.glob("*.yaml") if not f.name.startswith("_"))

        raise SpecLoadError(f"Version not found: {profile_name} v{version}")

    def list_versions(self: Self, profile: str | None = None) -> list[str]:
        """List available versions for a profile.

        Args:
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            List of version strings (e.g., ["1.1"]).
        """
        profile_name = (profile or self._default_profile).lower()
        versions = set()

        # Check for unified profile files
        for f in self._specs_dir.glob(f"{profile_name}_v*.yaml"):
            match = re.search(r"v(\d+\.\d+)", f.name)
            if match:
                versions.add(match.group(1))

        # Also check variant without underscore
        for f in self._specs_dir.glob(f"{profile_name}*.yaml"):
            match = re.search(r"v(\d+\.\d+)", f.name)
            if match:
                versions.add(match.group(1))

        # Check for version directories (legacy, only for miappe)
        if profile_name == "miappe":
            for d in self._specs_dir.iterdir():
                if d.is_dir() and d.name.startswith("v"):
                    version = d.name[1:].replace("_", ".")
                    versions.add(version)

        return sorted(versions)

    def list_profiles(self: Self) -> list[str]:
        """List available profiles.

        Returns:
            List of profile names (e.g., ["miappe", "isa"]).
        """
        profiles = set()

        # Find all profile files by pattern *_v*.yaml
        for f in self._specs_dir.glob("*_v*.yaml"):
            # Extract profile name (before _v)
            match = re.match(r"([a-z]+)_v\d+", f.stem)
            if match:
                profiles.add(match.group(1))

        return sorted(profiles)

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
