"""Spec builder helpers (compatibility shim).

The spec authoring logic now lives in :mod:`metaseed.specs.builder` and the
persistence logic in :mod:`metaseed.specs.persistence`. This module re-exports
the functions the UI has historically imported so existing call sites keep
working, while delegating to the shared engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaseed.specs.builder import (
    SpecBuilder,
    validate_entity_name,
    validate_field_name,
)
from metaseed.specs.persistence import (
    delete_user_spec,
    get_custom_specs_dir,
    list_available_templates,
    list_user_specs,
    save_spec,
)

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec

__all__ = [
    "clone_spec",
    "create_empty_spec",
    "delete_user_spec",
    "get_custom_specs_dir",
    "list_available_templates",
    "list_user_specs",
    "save_spec",
    "spec_to_yaml",
    "validate_entity_name",
    "validate_field_name",
]


def create_empty_spec() -> ProfileSpec:
    """Create a new empty ProfileSpec scaffold."""
    return SpecBuilder.empty("", "0.1").spec


def clone_spec(profile: str, version: str) -> ProfileSpec:
    """Deep copy an existing spec for use as a template.

    Raises:
        ValueError: If the profile/version cannot be loaded.
    """
    return SpecBuilder.from_template(profile, version).spec


def spec_to_yaml(spec: ProfileSpec) -> str:
    """Convert a ProfileSpec to a YAML string."""
    return SpecBuilder.from_spec(spec).to_yaml()
