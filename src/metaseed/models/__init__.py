"""Model generation module.

This module provides the public API for accessing models from various profiles
(MIAPPE, ISA, etc.), dynamically generating them from specifications when needed.
"""

from typing import cast

from pydantic import BaseModel

from metaseed.models.factory import (
    ModelContext,
    create_model_from_spec,
    get_global_context,
    set_model_context,
    set_model_loader,
)
from metaseed.models.types import OntologyTerm
from metaseed.specs.loader import SpecLoader
from metaseed.utils import to_snake_case

__all__ = [
    "ModelContext",
    "OntologyTerm",
    "create_model_from_spec",
    "get_global_context",
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
        SpecLoadError: If the entity specification is not found, which is also
            what an entity that cannot be generated reports.

    Example:
        >>> # MIAPPE model (default)
        >>> Investigation = get_model("Investigation", version="1.1")
        >>> inv = Investigation(unique_id="INV1", title="My Investigation")
        >>>
        >>> # ISA model
        >>> Study = get_model("Study", version="1.0", profile="isa")
        >>> study = Study(identifier="STU-001", title="My Study")
    """
    # Set context for nested entity resolution
    set_model_context(profile.lower(), version)

    # Load the spec so the cache key equals the real class name (spec.name).
    # Profile specs are cached by the loader, so this is cheap on cache hits.
    loader = SpecLoader(profile=profile)
    # Convert CamelCase to snake_case for case-insensitive file lookup
    entity_name = to_snake_case(name)
    spec = loader.load_entity(entity_name, version)

    # ONE cache: the ModelContext that nested-entity resolution reads. A
    # second registry with its own key scheme held a different class for the
    # same entity whenever one cache was populated without the other, so
    # nested conversion could return instances of a class the facade's
    # helper never saw.
    context = get_global_context()
    cached = context.peek(profile.lower(), version, spec.name)
    if cached is not None:
        return cached

    return cast("type[BaseModel]", create_model_from_spec(spec))


# Initialize the model loader for nested entity resolution
set_model_loader(get_model)
