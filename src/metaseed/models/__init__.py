"""Model generation module.

This module provides the public API for accessing models from various profiles
(MIAPPE, ISA, etc.), dynamically generating them from specifications when needed.
"""

from pydantic import BaseModel

from metaseed.models.factory import (
    ModelContext,
    create_model_from_spec,
    get_global_context,
    set_model_context,
    set_model_loader,
)
from metaseed.models.registry import (
    ModelNotFoundError,
    ModelRegistry,
    get_global_registry,
)
from metaseed.models.types import OntologyTerm
from metaseed.specs.loader import SpecLoader
from metaseed.utils import to_snake_case

__all__ = [
    "ModelContext",
    "ModelNotFoundError",
    "ModelRegistry",
    "OntologyTerm",
    "create_model_from_spec",
    "get_global_context",
    "get_global_registry",
    "get_model",
]


def get_model(
    name: str, version: str = "1.2", profile: str = "miappe"
) -> type[BaseModel]:
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

    # Include profile in cache key
    cache_version = f"{profile.lower()}:{version}"

    # Set context for nested entity resolution
    set_model_context(profile.lower(), version)

    # Load the spec so the registry key equals the real class name (spec.name).
    # Profile specs are cached by the loader, so this is cheap on cache hits.
    loader = SpecLoader(profile=profile)
    # Convert CamelCase to snake_case for case-insensitive file lookup
    entity_name = to_snake_case(name)
    spec = loader.load_entity(entity_name, version)

    # Check if already cached, keyed by the spec's PascalCase name
    if registry.has(spec.name, cache_version):
        return registry.get(spec.name, cache_version)

    model = create_model_from_spec(spec)
    registry.register(spec.name, cache_version, model)

    return model


# Initialize the model loader for nested entity resolution
set_model_loader(get_model)
