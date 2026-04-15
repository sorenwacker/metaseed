"""Model generation module.

This module provides the public API for accessing models from various profiles
(MIAPPE, ISA, etc.), dynamically generating them from specifications when needed.
"""

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

from metaseed.models.factory import create_model_from_spec, set_model_context, set_model_loader
from metaseed.models.registry import (
    ModelNotFoundError,
    ModelRegistry,
    get_global_registry,
)
from metaseed.models.types import OntologyTerm
from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    pass

__all__ = [
    "ModelNotFoundError",
    "ModelRegistry",
    "OntologyTerm",
    "create_model_from_spec",
    "get_global_registry",
    "get_model",
]


def _to_snake_case(name: str) -> str:
    """Convert CamelCase or PascalCase to snake_case.

    Args:
        name: Name in CamelCase (e.g., "BiologicalMaterial").

    Returns:
        Name in snake_case (e.g., "biological_material").
    """
    # Insert underscore before uppercase letters and convert to lowercase
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def get_model(name: str, version: str = "1.1", profile: str = "miappe") -> type[BaseModel]:
    """Get a model by name, version, and profile.

    Models are cached after first generation. If the model is not in the
    registry, it will be generated from the corresponding YAML specification.

    Args:
        name: Model name (e.g., "Investigation"). Case-insensitive for lookup,
            but the returned model will have proper PascalCase name.
        version: Profile version (e.g., "1.1" for MIAPPE, "1.0" for ISA).
        profile: Profile name (e.g., "miappe", "isa"). Defaults to "miappe".

    Returns:
        Pydantic model class for the specified entity.

    Raises:
        SpecLoadError: If the entity specification is not found.
        ModelNotFoundError: If the model cannot be generated.

    Example:
        >>> # MIAPPE model (default)
        >>> Investigation = get_model("Investigation", version="1.1")
        >>> inv = Investigation(unique_id="INV1", title="My Investigation")
        >>>
        >>> # ISA model
        >>> Study = get_model("Study", version="1.0", profile="isa")
        >>> study = Study(identifier="STU-001", title="My Study")
    """
    registry = get_global_registry()

    # Normalize name to PascalCase for registry lookup
    normalized_name = name.title().replace("_", "")

    # Include profile in cache key
    cache_version = f"{profile.lower()}:{version}"

    # Set context for nested entity resolution
    set_model_context(profile.lower(), version)

    # Check if already cached
    if registry.has(normalized_name, cache_version):
        return registry.get(normalized_name, cache_version)

    # Load spec and create model
    loader = SpecLoader(profile=profile)
    try:
        # Convert CamelCase to snake_case for file lookup
        entity_name = _to_snake_case(name)
        spec = loader.load_entity(entity_name, version)
    except SpecLoadError:
        raise

    model = create_model_from_spec(spec)
    registry.register(normalized_name, cache_version, model)

    return model


# Initialize the model loader for nested entity resolution
set_model_loader(get_model)
