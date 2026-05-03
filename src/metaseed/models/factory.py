"""Model factory for generating Pydantic models from specs.

This module provides the core functionality to dynamically create Pydantic
models from YAML specifications.
"""

from __future__ import annotations

import contextlib
import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, create_model, model_validator

from metaseed.models.types import OntologyTerm
from metaseed.specs.schema import PRIMITIVE_TYPES, EntitySpec, FieldSpec, FieldType

if TYPE_CHECKING:
    from collections.abc import Callable


class ModelContext:
    """Context for model resolution during deserialization.

    Encapsulates the profile context and model registry used when
    resolving nested entity types during model creation and validation.

    Attributes:
        profile: Current profile name (e.g., "miappe", "isa").
        version: Current profile version (e.g., "1.1").
    """

    def __init__(self, profile: str = "miappe", version: str = "1.1") -> None:
        """Initialize the model context.

        Args:
            profile: Profile name.
            version: Profile version.
        """
        self._profile = profile
        self._version = version
        self._models: dict[str, type[BaseModel]] = {}
        self._loader: Callable[[str, str, str], type[BaseModel]] | None = None

    @property
    def profile(self: Self) -> str:
        """Current profile name."""
        return self._profile

    @property
    def version(self: Self) -> str:
        """Current profile version."""
        return self._version

    def set_context(self: Self, profile: str, version: str) -> None:
        """Set the current profile context.

        Args:
            profile: Profile name.
            version: Profile version.
        """
        self._profile = profile
        self._version = version

    def set_loader(self: Self, loader: Callable[[str, str, str], type[BaseModel]]) -> None:
        """Set the model loader function.

        Args:
            loader: Function to load models on demand. Takes (name, version, profile).
        """
        self._loader = loader

    def register(
        self: Self, name: str, model: type[BaseModel], profile: str = "", version: str = ""
    ) -> None:
        """Register a model for nested entity resolution.

        Args:
            name: Model name.
            model: Model class.
            profile: Profile name (uses current if empty).
            version: Profile version (uses current if empty).
        """
        p = profile or self._profile
        v = version or self._version
        key = f"{p}:{v}:{name}"
        self._models[key] = model

    def get(self: Self, name: str) -> type[BaseModel] | None:
        """Get a registered model by name using current profile context.

        If the model is not in the registry but a loader is available,
        attempt to load it on demand.

        Args:
            name: Model name.

        Returns:
            Model class or None if not found.
        """
        key = f"{self._profile}:{self._version}:{name}"
        model = self._models.get(key)

        if model is None and self._loader is not None:
            with contextlib.suppress(Exception):
                model = self._loader(name, self._version, self._profile)

        return model


# Global context instance - required for model validation which happens
# at deserialization time and needs access to the context
_global_context = ModelContext()


def get_global_context() -> ModelContext:
    """Get the global model context.

    Returns:
        The global ModelContext instance.
    """
    return _global_context


def set_model_loader(loader: Any) -> None:
    """Set the model loader function for lazy loading nested entities.

    Args:
        loader: Function to load models on demand.
    """
    _global_context.set_loader(loader)


def set_model_context(profile: str, version: str) -> None:
    """Set the current profile context for nested entity resolution.

    Args:
        profile: Profile name.
        version: Profile version.
    """
    _global_context.set_context(profile, version)


def register_model(name: str, model: type[BaseModel], profile: str = "", version: str = "") -> None:
    """Register a model for nested entity resolution.

    Args:
        name: Model name.
        model: Model class.
        profile: Profile name (uses current if empty).
        version: Profile version (uses current if empty).
    """
    _global_context.register(name, model, profile, version)


def get_registered_model(name: str) -> type[BaseModel] | None:
    """Get a registered model by name using current profile context.

    Args:
        name: Model name.

    Returns:
        Model class or None if not found.
    """
    return _global_context.get(name)


def _coerce_string_to_entity(value: str, model_class: type[BaseModel]) -> BaseModel | str:
    """Coerce a string value to an entity model if appropriate.

    Only coerces when the target model has a simple primary field pattern:
    - OntologyAnnotation-like: has "term" field -> {"term": "value"}
    - Comment-like: has "value" field -> {"value": "value"}

    Does NOT coerce when the model has complex required fields (like study_id),
    as these are likely string references that should remain as strings.

    Args:
        value: String value to potentially coerce.
        model_class: Target model class.

    Returns:
        Model instance if coercion is appropriate, original string otherwise.
    """
    model_fields = model_class.model_fields

    # Only coerce if the model has a simple primary field pattern
    # These are annotation-like entities where a single string makes sense
    simple_primary_fields = ["term", "value", "text"]

    for field_name in simple_primary_fields:
        if field_name in model_fields:
            # Check if this is the only required field (simple entity)
            required_fields = [name for name, info in model_fields.items() if info.is_required()]
            if len(required_fields) <= 1:
                try:
                    return model_class.model_validate({field_name: value})
                except Exception:
                    # If validation fails, keep as string
                    return value

    # Don't coerce - likely a string reference (e.g., derives_from: ["source_name"])
    return value


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
        """Convert nested dicts to their proper model types.

        Also handles type coercion for common cases:
        - Strings in list[OntologyAnnotation] are coerced to {"term": string}
        - This allows simplified example data like roles: ["principal investigator"]
          to work with schemas expecting list[OntologyAnnotation]
        """
        if not isinstance(data, dict):
            return data

        entity_fields = getattr(cls, "__entity_fields__", {})

        for field_name, entity_type in entity_fields.items():
            if field_name not in data:
                continue

            value = data[field_name]
            model_class = get_registered_model(entity_type)

            if model_class is None:
                continue

            if isinstance(value, list):
                converted = []
                for item in value:
                    if isinstance(item, dict):
                        converted.append(model_class.model_validate(item))
                    elif isinstance(item, str):
                        # Coerce strings to objects for OntologyAnnotation-like entities
                        # These typically have a "term" field as the primary identifier
                        converted.append(_coerce_string_to_entity(item, model_class))
                    else:
                        converted.append(item)
                data[field_name] = converted
            elif isinstance(value, dict):
                data[field_name] = model_class.model_validate(value)
            elif isinstance(value, str):
                # Coerce single string to entity
                data[field_name] = _coerce_string_to_entity(value, model_class)

        return data


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
    FieldType.ENTITY: Any,
}


def _build_field_type(field: FieldSpec) -> type:
    """Build the Python type for a field spec.

    Args:
        field: Field specification.

    Returns:
        Python type appropriate for the field.
    """
    base_type = TYPE_MAP.get(field.type, str)

    if field.type == FieldType.LIST:
        return list[Any]

    if field.type == FieldType.ENTITY:
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

    if constraints.pattern:
        kwargs["pattern"] = constraints.pattern
    if constraints.min_length is not None:
        kwargs["min_length"] = constraints.min_length
    if constraints.max_length is not None:
        kwargs["max_length"] = constraints.max_length

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

    if field.constraints and field.constraints.enum:
        python_type = _build_enum_type(field.constraints.enum)

    if field.type == FieldType.LIST:
        constraints["default_factory"] = list
        return (Annotated[python_type, Field(**constraints)], ...)

    if field.type == FieldType.ENTITY:
        annotated_type = (
            Annotated[python_type, Field(**constraints)] if constraints else python_type
        )
        if field.required:
            return (annotated_type, ...)
        return (annotated_type | None, None)

    annotated_type = Annotated[python_type, Field(**constraints)] if constraints else python_type

    if field.required:
        if constraints:
            return (annotated_type, ...)
        return (python_type, ...)
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

        if field.type == FieldType.LIST and field.items:
            if field.items not in PRIMITIVE_TYPES:
                entity_fields[field.name] = field.items
        elif field.type == FieldType.ENTITY and field.items:
            entity_fields[field.name] = field.items

    model = create_model(
        spec.name,
        __base__=MIAPPEBaseModel,
        **field_definitions,
    )

    model.__entity_fields__ = entity_fields  # type: ignore[attr-defined]

    register_model(spec.name, model)

    return model
