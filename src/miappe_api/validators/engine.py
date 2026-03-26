"""Validation engine for running multiple rules.

This module provides the validation engine that coordinates rule execution.
"""

from typing import Any, Self

from miappe_api.specs.loader import SpecLoader
from miappe_api.validators.base import ValidationError, ValidationRule
from miappe_api.validators.rules import (
    DateRangeRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
)


class ValidationEngine:
    """Engine for running validation rules.

    Collects and runs validation rules against data, aggregating all
    errors from all rules.
    """

    def __init__(self: Self) -> None:
        """Initialize the engine with an empty rule list."""
        self.rules: list[ValidationRule] = []

    def add_rule(self: Self, rule: ValidationRule) -> Self:
        """Add a validation rule to the engine.

        Args:
            rule: Validation rule to add.

        Returns:
            Self for chaining.
        """
        self.rules.append(rule)
        return self

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Run all rules against the data.

        Args:
            data: Dictionary to validate.

        Returns:
            List of all validation errors from all rules.
        """
        errors: list[ValidationError] = []
        for rule in self.rules:
            errors.extend(rule.validate(data))
        return errors


def create_engine_for_entity(entity: str, version: str = "1.1") -> ValidationEngine:
    """Create a validation engine configured for a specific entity.

    Loads the entity spec and configures appropriate validation rules
    based on the spec's field definitions.

    Args:
        entity: Entity name (e.g., "investigation").
        version: MIAPPE version.

    Returns:
        Configured ValidationEngine instance.
    """
    loader = SpecLoader()
    spec = loader.load_entity(entity, version)

    engine = ValidationEngine()

    # Add required fields rule
    required_fields = [f.name for f in spec.get_required_fields()]
    if required_fields:
        engine.add_rule(RequiredFieldsRule(fields=required_fields))

    # Add ID pattern rule for unique_id fields
    for field in spec.fields:
        if field.name == "unique_id":
            engine.add_rule(UniqueIdPatternRule(field="unique_id"))
            break

    # Add date range rules for common date pairs
    date_fields = {f.name for f in spec.fields if f.type.value == "date"}
    if "start_date" in date_fields and "end_date" in date_fields:
        engine.add_rule(DateRangeRule(start_field="start_date", end_field="end_date"))

    return engine
