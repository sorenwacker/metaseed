"""Concrete validation rules.

This module provides common validation rules for MIAPPE entities.
"""

import datetime
import re
from typing import Any, Self

from miappe_api.validators.base import ValidationError, ValidationRule


class DateRangeRule(ValidationRule):
    """Validates that end date is not before start date.

    Attributes:
        start_field: Name of the start date field.
        end_field: Name of the end date field.
    """

    def __init__(self: Self, start_field: str, end_field: str) -> None:
        """Initialize the rule.

        Args:
            start_field: Name of the start date field.
            end_field: Name of the end date field.
        """
        self.start_field = start_field
        self.end_field = end_field

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return "date_range"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate that end date is not before start date.

        Args:
            data: Dictionary with date fields.

        Returns:
            List with one error if end_date < start_date, empty otherwise.
        """
        start = data.get(self.start_field)
        end = data.get(self.end_field)

        # Skip if either date is missing
        if start is None or end is None:
            return []

        # Convert strings to dates if needed
        if isinstance(start, str):
            start = datetime.date.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.date.fromisoformat(end)

        if end < start:
            return [
                ValidationError(
                    field=self.end_field,
                    message=f"{self.end_field} ({end}) must not be before {self.start_field} ({start})",
                    rule=self.name,
                )
            ]
        return []


class RequiredFieldsRule(ValidationRule):
    """Validates that required fields are present and non-empty.

    Attributes:
        fields: List of required field names.
    """

    def __init__(self: Self, fields: list[str]) -> None:
        """Initialize the rule.

        Args:
            fields: List of required field names.
        """
        self.fields = fields

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return "required_fields"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate that all required fields are present and non-empty.

        Args:
            data: Dictionary to validate.

        Returns:
            List of errors for missing or empty fields.
        """
        errors = []
        for field in self.fields:
            value = data.get(field)
            if value is None or value == "":
                errors.append(
                    ValidationError(
                        field=field,
                        message=f"Field '{field}' is required",
                        rule=self.name,
                    )
                )
        return errors


class UniqueIdPatternRule(ValidationRule):
    """Validates that unique IDs match the expected pattern.

    MIAPPE IDs should contain only alphanumeric characters, underscores,
    and hyphens.

    Attributes:
        field: Name of the ID field to validate.
        pattern: Regex pattern for valid IDs.
    """

    DEFAULT_PATTERN = r"^[A-Za-z0-9_-]+$"

    def __init__(self: Self, field: str, pattern: str | None = None) -> None:
        """Initialize the rule.

        Args:
            field: Name of the ID field.
            pattern: Optional custom regex pattern.
        """
        self.field = field
        self.pattern = re.compile(pattern or self.DEFAULT_PATTERN)

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return "unique_id_pattern"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate ID matches pattern.

        Args:
            data: Dictionary with ID field.

        Returns:
            List with one error if pattern doesn't match, empty otherwise.
        """
        value = data.get(self.field)

        # Skip if field is missing (use RequiredFieldsRule for that)
        if value is None:
            return []

        if not isinstance(value, str):
            return [
                ValidationError(
                    field=self.field,
                    message=f"Field '{self.field}' must be a string",
                    rule=self.name,
                )
            ]

        if not self.pattern.match(value):
            return [
                ValidationError(
                    field=self.field,
                    message=f"Field '{self.field}' contains invalid characters. "
                    "Only alphanumeric characters, underscores, and hyphens allowed.",
                    rule=self.name,
                )
            ]
        return []


class EntityReferenceRule(ValidationRule):
    """Validates that entity references point to existing entities.

    Used for cross-reference validation when entities reference other entities
    by ID fields (e.g., Study.geographic_location -> Location).

    Attributes:
        field: Name of the reference field.
        reference_id_field: Name of the ID field in the referenced entity.
        available_ids: Set of valid IDs that exist in the collection.
        is_list: Whether the field contains a list of references.
    """

    def __init__(
        self: Self,
        field: str,
        reference_id_field: str,
        available_ids: set[str],
        is_list: bool = False,
    ) -> None:
        """Initialize the rule.

        Args:
            field: Name of the field containing the reference.
            reference_id_field: Name of the ID field in referenced entities.
            available_ids: Set of valid entity IDs.
            is_list: True if field contains a list of references.
        """
        self.field = field
        self.reference_id_field = reference_id_field
        self.available_ids = available_ids
        self.is_list = is_list

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return "entity_reference"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate that all references point to existing entities.

        Args:
            data: Dictionary containing the reference field.

        Returns:
            List of errors for invalid references.
        """
        value = data.get(self.field)

        # Skip if field is missing or None
        if value is None:
            return []

        errors: list[ValidationError] = []

        if self.is_list:
            # Validate list of references
            if not isinstance(value, list):
                return errors
            for i, ref in enumerate(value):
                if isinstance(ref, dict):
                    ref_id = ref.get(self.reference_id_field)
                    if ref_id and ref_id not in self.available_ids:
                        errors.append(
                            ValidationError(
                                field=f"{self.field}[{i}]",
                                message=f"Reference '{ref_id}' not found in "
                                f"available {self.reference_id_field}s",
                                rule=self.name,
                            )
                        )
        else:
            # Validate single reference
            if isinstance(value, dict):
                ref_id = value.get(self.reference_id_field)
                if ref_id and ref_id not in self.available_ids:
                    errors.append(
                        ValidationError(
                            field=self.field,
                            message=f"Reference '{ref_id}' not found in "
                            f"available {self.reference_id_field}s",
                            rule=self.name,
                        )
                    )

        return errors


# Re-export ValidationError for convenience
__all__ = [
    "DateRangeRule",
    "EntityReferenceRule",
    "RequiredFieldsRule",
    "UniqueIdPatternRule",
    "ValidationError",
    "ValidationRule",
]
