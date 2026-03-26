"""Validation module for MIAPPE entities.

This module provides validation rules and engine for validating
MIAPPE-compliant metadata beyond basic type checking.
"""

from typing import Any

from miappe_api.validators.base import ValidationError, ValidationRule
from miappe_api.validators.engine import ValidationEngine, create_engine_for_entity
from miappe_api.validators.rules import (
    DateRangeRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
)

__all__ = [
    "DateRangeRule",
    "RequiredFieldsRule",
    "UniqueIdPatternRule",
    "ValidationEngine",
    "ValidationError",
    "ValidationRule",
    "create_engine_for_entity",
    "validate",
]


def validate(data: dict[str, Any], entity: str, version: str = "1.1") -> list[ValidationError]:
    """Validate data against entity rules.

    Convenience function that creates an engine for the entity and
    runs validation.

    Args:
        data: Dictionary of field values to validate.
        entity: Entity name (e.g., "investigation").
        version: MIAPPE version.

    Returns:
        List of validation errors. Empty if validation passes.

    Example:
        >>> errors = validate({"unique_id": "INV001"}, "investigation")
        >>> if errors:
        ...     for error in errors:
        ...         print(error)
    """
    engine = create_engine_for_entity(entity, version)
    return engine.validate(data)
