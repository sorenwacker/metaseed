"""Helper functions for the Spec Builder.

Provides utilities for creating, cloning, converting, and saving ProfileSpec
objects used by the spec builder UI.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec


def create_empty_spec() -> ProfileSpec:
    """Create a new empty ProfileSpec scaffold.

    Returns:
        A ProfileSpec with default values ready for editing.
    """
    from metaseed.specs.schema import ProfileSpec

    return ProfileSpec(
        version="1.0",
        name="",
        display_name="",
        description="",
        ontology=None,
        root_entity="",
        validation_rules=[],
        entities={},
    )


def clone_spec(profile: str, version: str) -> ProfileSpec:
    """Deep copy an existing spec for use as a template.

    Args:
        profile: Profile name (e.g., "miappe").
        version: Version string (e.g., "1.2").

    Returns:
        A deep copy of the ProfileSpec that can be modified independently.

    Raises:
        ValueError: If the profile/version cannot be loaded.
    """
    from metaseed.specs.loader import SpecLoader

    loader = SpecLoader(profile=profile)
    try:
        spec = loader.load_profile(version=version, profile=profile)
    except Exception as e:
        raise ValueError(f"Cannot load profile {profile} v{version}: {e}") from e

    # Deep copy to ensure independence from cached version
    return copy.deepcopy(spec)


def spec_to_yaml(spec: ProfileSpec) -> str:
    """Convert a ProfileSpec to YAML string.

    Args:
        spec: The ProfileSpec to convert.

    Returns:
        YAML string representation of the spec.
    """
    # Convert to dict, handling Pydantic models
    data = spec.model_dump(exclude_none=True, exclude_defaults=False)

    # Custom representer for cleaner output
    def str_representer(dumper: yaml.Dumper, data: str) -> yaml.Node:
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.add_representer(str, str_representer)

    return yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )


def spec_to_dict(spec: ProfileSpec) -> dict:
    """Convert a ProfileSpec to a dictionary.

    Args:
        spec: The ProfileSpec to convert.

    Returns:
        Dictionary representation of the spec.
    """
    return spec.model_dump(exclude_none=True, exclude_defaults=False)


def get_custom_specs_dir() -> Path:
    """Get the directory for saving custom specs.

    Creates the directory if it doesn't exist.

    Returns:
        Path to the custom specs directory.
    """
    specs_dir = Path(__file__).parent.parent / "specs"
    return specs_dir


def save_spec(spec: ProfileSpec, name: str | None = None) -> Path:
    """Save a ProfileSpec to the filesystem.

    Saves to specs/<name>/<version>/profile.yaml structure.

    Args:
        spec: The ProfileSpec to save.
        name: Profile name override. Uses spec.name if not provided.

    Returns:
        Path to the saved profile.yaml file.

    Raises:
        ValueError: If name is empty or invalid.
    """
    profile_name = (name or spec.name).lower().strip()
    if not profile_name:
        raise ValueError("Profile name cannot be empty")

    # Sanitize name for filesystem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in profile_name)

    specs_dir = get_custom_specs_dir()
    version_dir = specs_dir / safe_name / spec.version
    version_dir.mkdir(parents=True, exist_ok=True)

    profile_path = version_dir / "profile.yaml"
    yaml_content = spec_to_yaml(spec)
    profile_path.write_text(yaml_content, encoding="utf-8")

    return profile_path


def list_available_templates() -> list[dict]:
    """List available profiles that can be used as templates.

    Returns:
        List of dicts with profile info: name, display_name, versions.
    """
    from metaseed.specs.loader import SpecLoader

    loader = SpecLoader()
    profiles = loader.list_profiles()

    result = []
    for profile_name in profiles:
        versions = loader.list_versions(profile_name)
        if not versions:
            continue

        # Get display info from latest version
        try:
            latest = versions[-1]
            spec = loader.load_profile(version=latest, profile=profile_name)
            result.append(
                {
                    "name": profile_name,
                    "display_name": spec.display_name or profile_name.upper(),
                    "description": spec.description or "",
                    "versions": versions,
                }
            )
        except Exception:
            result.append(
                {
                    "name": profile_name,
                    "display_name": profile_name.upper(),
                    "description": "",
                    "versions": versions,
                }
            )

    return result


def validate_entity_name(name: str) -> str | None:
    """Validate an entity name.

    Args:
        name: The entity name to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Entity name is required"
    if not name[0].isupper():
        return "Entity name must start with uppercase letter (PascalCase)"
    if not name.replace("_", "").isalnum():
        return "Entity name can only contain letters, numbers, and underscores"
    return None


def validate_field_name(name: str) -> str | None:
    """Validate a field name.

    Args:
        name: The field name to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Field name is required"
    if not name[0].islower() and name[0] != "_":
        return "Field name must start with lowercase letter (snake_case)"
    if not name.replace("_", "").isalnum():
        return "Field name can only contain letters, numbers, and underscores"
    return None
