"""Model factory for generating Pydantic models from specs.

This module provides the core functionality to dynamically create Pydantic
models from YAML specifications.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, create_model, model_validator

from metaseed.models.types import OntologyTerm
from metaseed.specs.schema import EntitySpec, FieldSpec, FieldType

if TYPE_CHECKING:
    pass

# Registry for resolving entity types during deserialization
# Keys are "profile:version:name" to support multiple profiles
_MODEL_REGISTRY: dict[str, type[BaseModel]] = {}

# Current profile context for nested entity resolution
_CURRENT_PROFILE: str = "miappe"
_CURRENT_VERSION: str = "1.1"

# Lazy loader function (set by __init__.py to avoid circular imports)
_MODEL_LOADER: Any = None


def set_model_loader(loader: Any) -> None:
    """Set the model loader function for lazy loading nested entities."""
    global _MODEL_LOADER
    _MODEL_LOADER = loader


def set_model_context(profile: str, version: str) -> None:
    """Set the current profile context for nested entity resolution."""
    global _CURRENT_PROFILE, _CURRENT_VERSION
    _CURRENT_PROFILE = profile
    _CURRENT_VERSION = version


def register_model(name: str, model: type[BaseModel], profile: str = "", version: str = "") -> None:
    """Register a model for nested entity resolution."""
    # Use provided profile/version or fall back to current context
    p = profile or _CURRENT_PROFILE
    v = version or _CURRENT_VERSION
    key = f"{p}:{v}:{name}"
    _MODEL_REGISTRY[key] = model


def get_registered_model(name: str) -> type[BaseModel] | None:
    """Get a registered model by name using current profile context.

    If the model is not in the registry but a loader is available,
    attempt to load it on demand.
    """
    key = f"{_CURRENT_PROFILE}:{_CURRENT_VERSION}:{name}"
    model = _MODEL_REGISTRY.get(key)

    if model is None and _MODEL_LOADER is not None:
        # Try to load the model on demand (silently fail if not found)
        import contextlib

        with contextlib.suppress(Exception):
            model = _MODEL_LOADER(name, version=_CURRENT_VERSION, profile=_CURRENT_PROFILE)

    return model


class MIAPPEBaseModel(BaseModel):
    """Base model for all MIAPPE/ISA entities.

    Provides validation on assignment, JSON serialization mode, and
    automatic nested entity deserialization.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    @model_validator(mode="before")
    @classmethod
    def _convert_nested_entities(cls, data: Any) -> Any:
        """Convert nested dicts to their proper model types."""
        if not isinstance(data, dict):
            return data

        # Get field metadata from class
        entity_fields = getattr(cls, "__entity_fields__", {})

        for field_name, entity_type in entity_fields.items():
            if field_name not in data:
                continue

            value = data[field_name]
            model_class = get_registered_model(entity_type)

            if model_class is None:
                continue

            # Handle list of entities
            if isinstance(value, list):
                converted = []
                for item in value:
                    if isinstance(item, dict):
                        converted.append(model_class.model_validate(item))
                    else:
                        converted.append(item)
                data[field_name] = converted
            # Handle single entity
            elif isinstance(value, dict):
                data[field_name] = model_class.model_validate(value)

        return data


# Type mapping from spec types to Python types
TYPE_MAP: dict[FieldType, type] = {
    FieldType.STRING: str,
    FieldType.INTEGER: int,
    FieldType.FLOAT: float,
    FieldType.BOOLEAN: bool,
    FieldType.DATE: datetime.date,
    FieldType.DATETIME: datetime.datetime,
    FieldType.URI: AnyUrl,
    FieldType.ONTOLOGY_TERM: OntologyTerm,
    FieldType.LIST: list,
    FieldType.ENTITY: Any,  # Reference to another entity
}


def _build_field_type(field: FieldSpec) -> type:
    """Build the Python type for a field spec.

    Args:
        field: Field specification.

    Returns:
        Python type appropriate for the field.
    """
    base_type = TYPE_MAP.get(field.type, str)

    # Handle list types
    if field.type == FieldType.LIST:
        # For now, treat all list items as Any since we don't have
        # the referenced model available during creation
        # In future phases, this could resolve to actual model types
        return list[Any]

    # Handle entity references
    if field.type == FieldType.ENTITY:
        # For now, treat as Any since we don't have the referenced model
        # available during creation. Could resolve to actual model types later.
        return Any

    return base_type


def _build_field_constraints(field: FieldSpec) -> dict[str, Any]:
    """Build Field constraints from spec constraints.

    Args:
        field: Field specification.

    Returns:
        Dict of Field parameter kwargs.
    """
    kwargs: dict[str, Any] = {}

    if field.description:
        kwargs["description"] = field.description

    constraints = field.constraints
    if constraints is None:
        return kwargs

    # String constraints
    if constraints.pattern:
        kwargs["pattern"] = constraints.pattern
    if constraints.min_length is not None:
        kwargs["min_length"] = constraints.min_length
    if constraints.max_length is not None:
        kwargs["max_length"] = constraints.max_length

    # Numeric constraints
    if constraints.minimum is not None:
        kwargs["ge"] = constraints.minimum
    if constraints.maximum is not None:
        kwargs["le"] = constraints.maximum

    return kwargs


def _build_enum_type(enum_values: list[str]) -> type:
    """Build a Literal type from enum values.

    Args:
        enum_values: List of allowed string values.

    Returns:
        A Literal type constraining values to the given list.
    """
    # Create Literal type from the enum values
    return Literal[tuple(enum_values)]  # type: ignore[misc]


def _create_field_definition(field: FieldSpec) -> tuple[type, Any]:
    """Create a Pydantic field definition tuple.

    Args:
        field: Field specification.

    Returns:
        Tuple of (type, default) for pydantic.create_model.
    """
    python_type = _build_field_type(field)
    constraints = _build_field_constraints(field)

    # Check if field has enum constraint - use Literal type instead
    if field.constraints and field.constraints.enum:
        python_type = _build_enum_type(field.constraints.enum)

    # List fields default to empty list for easier use
    if field.type == FieldType.LIST:
        constraints["default_factory"] = list
        return (Annotated[python_type, Field(**constraints)], ...)

    # Entity references are optional by default
    if field.type == FieldType.ENTITY:
        annotated_type = (
            Annotated[python_type, Field(**constraints)] if constraints else python_type
        )
        if field.required:
            return (annotated_type, ...)
        return (annotated_type | None, None)

    annotated_type = Annotated[python_type, Field(**constraints)] if constraints else python_type

    if field.required:
        # Required field with no default
        if constraints:
            return (annotated_type, ...)
        return (python_type, ...)
    # Optional field defaults to None
    return (annotated_type | None, None)


def create_model_from_spec(spec: EntitySpec) -> type:
    """Create a Pydantic model from an entity specification.

    Args:
        spec: Entity specification defining the model structure.

    Returns:
        Dynamically created Pydantic model class.

    Example:
        >>> from metaseed.specs import SpecLoader
        >>> loader = SpecLoader()
        >>> spec = loader.load_entity("investigation", "1.1")
        >>> Investigation = create_model_from_spec(spec)
        >>> inv = Investigation(unique_id="INV1", title="My Investigation")
        >>> inv.studies.append(study)  # Standard Python list operations
    """
    field_definitions: dict[str, Any] = {}
    entity_fields: dict[str, str] = {}

    for field in spec.fields:
        field_definitions[field.name] = _create_field_definition(field)

        # Track fields that reference other entities for deserialization
        if field.type == FieldType.LIST and field.items:
            # Don't track primitive list types
            if field.items not in ("string", "int", "float", "bool"):
                entity_fields[field.name] = field.items
        elif field.type == FieldType.ENTITY and field.items:
            entity_fields[field.name] = field.items

    model = create_model(
        spec.name,
        __base__=MIAPPEBaseModel,
        **field_definitions,
    )

    # Store entity field metadata for nested deserialization
    model.__entity_fields__ = entity_fields  # type: ignore[attr-defined]

    # Register model for resolution by other models
    register_model(spec.name, model)

    return model
