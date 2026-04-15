"""Validation module for MIAPPE entities.

This module provides validation rules and engine for validating
MIAPPE-compliant metadata beyond basic type checking.
"""

import re
from typing import Any

from pydantic import BaseModel

from metaseed.validators.base import ValidationError, ValidationRule
from metaseed.validators.dataset import DatasetValidationResult, DatasetValidator
from metaseed.validators.engine import ValidationEngine, create_engine_for_entity
from metaseed.validators.rules import (
    DateRangeRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
)

__all__ = [
    "DatasetValidationResult",
    "DatasetValidator",
    "DateRangeRule",
    "RequiredFieldsRule",
    "UniqueIdPatternRule",
    "ValidationEngine",
    "ValidationError",
    "ValidationRule",
    "create_engine_for_entity",
    "validate",
]


def _to_snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _validate_nested(
    data: dict[str, Any],
    entity: str,
    version: str,
    profile: str = "miappe",
    path: str = "",
) -> list[ValidationError]:
    """Recursively validate data and nested entities.

    Args:
        data: Dictionary to validate.
        entity: Entity type name.
        version: Profile version.
        profile: Profile name.
        path: Current path for error reporting.

    Returns:
        List of all validation errors including nested ones.
    """
    from metaseed.specs.loader import SpecLoader

    errors: list[ValidationError] = []

    # Validate current entity
    engine = create_engine_for_entity(entity, version, profile=profile)
    for error in engine.validate(data):
        # Prefix field with path for nested errors
        field = f"{path}.{error.field}" if path else error.field
        errors.append(ValidationError(field=field, message=error.message, rule=error.rule))

    # Find and validate nested list fields
    loader = SpecLoader(profile=profile)
    try:
        spec = loader.load_entity(entity, version)
    except Exception:
        return errors

    for field in spec.fields:
        if field.type.value == "list" and field.items:
            items = data.get(field.name, [])
            if not items:
                continue

            # Check if items is a known entity type
            item_entity = _to_snake_case(field.items)
            try:
                loader.load_entity(item_entity, version)
            except Exception:
                continue

            # Validate each item in the list
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    item_path = f"{path}.{field.name}[{i}]" if path else f"{field.name}[{i}]"
                    errors.extend(_validate_nested(item, item_entity, version, profile, item_path))

    return errors


def validate(
    data: dict[str, Any] | BaseModel,
    entity: str | None = None,
    version: str = "1.1",
    profile: str = "miappe",
    cascade: bool = True,
) -> list[ValidationError]:
    """Validate data against entity rules.

    Supports both dict and Pydantic model instances. When cascade=True,
    recursively validates nested entities.

    Args:
        data: Dictionary or Pydantic model to validate.
        entity: Entity name (e.g., "investigation"). Auto-detected from
            model class name if data is a BaseModel and entity is None.
        version: Profile version.
        profile: Profile name (e.g., "miappe", "isa").
        cascade: If True, recursively validate nested entities.

    Returns:
        List of validation errors. Empty if validation passes.

    Example:
        >>> # Validate a dict
        >>> errors = validate({"unique_id": "INV001"}, "investigation")

        >>> # Validate a model instance (entity auto-detected)
        >>> inv = Investigation(unique_id="INV001", title="Test")
        >>> errors = validate(inv)

        >>> # Cascade validation to nested entities
        >>> inv.studies.append(Study(unique_id="STU001", title="Study"))
        >>> errors = validate(inv, cascade=True)
    """
    # Handle Pydantic model instances
    if isinstance(data, BaseModel):
        if entity is None:
            entity = _to_snake_case(data.__class__.__name__)
        data = data.model_dump(mode="json")

    if entity is None:
        raise ValueError("entity must be specified when data is a dict")

    if cascade:
        return _validate_nested(data, entity, version, profile)

    engine = create_engine_for_entity(entity, version, profile=profile)
    return engine.validate(data)
