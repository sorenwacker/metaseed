"""Concrete validation rules.

This module provides common validation rules for MIAPPE entities.
"""

import datetime
import re
from typing import Any, Self

from metaseed.validators.base import ValidationError, ValidationRule, has_value


class DateRangeRule(ValidationRule):
    """Validates that end date is not before start date.

    Attributes:
        start_field: Name of the start date field.
        end_field: Name of the end date field.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        start_field: str,
        end_field: str,
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            start_field: Name of the start date field.
            end_field: Name of the end date field.
            message: Optional custom error message.
        """
        self.start_field = start_field
        self.end_field = end_field
        self.custom_message = message

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
        start_raw = data.get(self.start_field)
        end_raw = data.get(self.end_field)

        # Skip if either date is missing or empty
        if not start_raw or not end_raw:
            return []

        # Convert strings to dates if needed. The engine runs against raw,
        # un-coerced YAML data, so a malformed date string must be reported as a
        # validation error rather than allowed to crash the whole run.
        errors: list[ValidationError] = []
        start = self._parse_date(start_raw, self.start_field, errors)
        end = self._parse_date(end_raw, self.end_field, errors)
        if errors:
            return errors

        if end < start:
            msg = (
                self.custom_message
                or f"{self.end_field} ({end}) must not be before {self.start_field} ({start})"
            )
            return [
                ValidationError(
                    field=self.end_field,
                    message=msg,
                    rule=self.name,
                )
            ]
        return []

    def _parse_date(
        self: Self,
        value: Any,
        field: str,
        errors: list[ValidationError],
    ) -> datetime.date | None:
        """Coerce a raw value to a date, recording an error on failure.

        Args:
            value: Raw field value (date, datetime, or ISO string).
            field: Field name, used in the error message.
            errors: List that a parse failure is appended to.

        Returns:
            The parsed date, or None if the value could not be parsed.
        """
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            try:
                if "T" in value:
                    return datetime.datetime.fromisoformat(value).date()
                return datetime.date.fromisoformat(value)
            except ValueError:
                errors.append(
                    ValidationError(
                        field=field,
                        message=f"Field '{field}' is not a valid date: {value!r}",
                        rule=self.name,
                    )
                )
                return None
        errors.append(
            ValidationError(
                field=field,
                message=f"Field '{field}' is not a valid date: {value!r}",
                rule=self.name,
            )
        )
        return None


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
            if not has_value(data, field):
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
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        field: str,
        reference_id_field: str,
        available_ids: set[str],
        is_list: bool = False,
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            field: Name of the field containing the reference.
            reference_id_field: Name of the ID field in referenced entities.
            available_ids: Set of valid entity IDs.
            is_list: True if field contains a list of references.
            message: Optional custom error message.
        """
        self.field = field
        self.reference_id_field = reference_id_field
        self.available_ids = available_ids
        self.is_list = is_list
        self.custom_message = message

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
                        msg = (
                            self.custom_message
                            or f"Reference '{ref_id}' not found in "
                            f"available {self.reference_id_field}s"
                        )
                        errors.append(
                            ValidationError(
                                field=f"{self.field}[{i}]",
                                message=msg,
                                rule=self.name,
                            )
                        )
        # Validate single reference
        elif isinstance(value, dict):
            ref_id = value.get(self.reference_id_field)
            if ref_id and ref_id not in self.available_ids:
                msg = (
                    self.custom_message
                    or f"Reference '{ref_id}' not found in available {self.reference_id_field}s"
                )
                errors.append(
                    ValidationError(
                        field=self.field,
                        message=msg,
                        rule=self.name,
                    )
                )

        return errors


class ConditionalRule(ValidationRule):
    """Validates conditional field requirements.

    Supports simple conditions like:
    - "A OR B" - at least one must be present
    - "A AND B" - both must be present
    - "(NOT A) OR B" - if A missing, B not required; if A present, B required
    - "(A AND B) OR (NOT A AND NOT B)" - both or neither

    Attributes:
        condition: Condition expression string.
        rule_name: Name for this specific rule instance.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        condition: str,
        rule_name: str = "conditional",
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            condition: Condition expression (e.g., "A OR B").
            rule_name: Name for this rule instance.
            message: Optional custom error message.
        """
        self.condition = condition
        self.rule_name = rule_name
        self.custom_message = message
        self._fields = self._extract_fields(condition)

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return self.rule_name

    def _extract_fields(self: Self, condition: str) -> list[str]:
        """Extract field names from condition."""
        # Remove operators and parentheses
        cleaned = condition.replace("(", " ").replace(")", " ")
        tokens = cleaned.split()
        # Filter out operators
        operators = {"AND", "OR", "NOT"}
        return [t for t in tokens if t not in operators]

    def _evaluate(self: Self, condition: str, data: dict[str, Any]) -> bool:
        """Evaluate condition expression."""
        # Simple parser for common patterns
        condition = condition.strip()

        # Handle parentheses by recursive evaluation
        while "(" in condition:
            # Find innermost parentheses
            start = condition.rfind("(")
            end = condition.find(")", start)
            if end == -1:
                break
            inner = condition[start + 1 : end]
            result = self._evaluate(inner, data)
            condition = (
                condition[:start]
                + ("TRUE" if result else "FALSE")
                + condition[end + 1 :]
            )

        # Handle NOT
        condition = condition.replace("NOT TRUE", "FALSE")
        condition = condition.replace("NOT FALSE", "TRUE")

        # Replace field names with TRUE/FALSE
        for field in self._fields:
            has_val = "TRUE" if has_value(data, field) else "FALSE"
            condition = re.sub(
                rf"\bNOT\s+{re.escape(field)}\b",
                "FALSE" if has_val == "TRUE" else "TRUE",
                condition,
            )
            condition = re.sub(rf"\b{re.escape(field)}\b", has_val, condition)

        # Evaluate AND/OR
        condition = condition.strip()

        if " OR " in condition:
            parts = condition.split(" OR ")
            return any(self._evaluate(p.strip(), data) for p in parts)

        if " AND " in condition:
            parts = condition.split(" AND ")
            return all(self._evaluate(p.strip(), data) for p in parts)

        return condition.strip() == "TRUE"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate conditional requirement.

        Args:
            data: Dictionary to validate.

        Returns:
            List with error if condition not met.
        """
        if not self._evaluate(self.condition, data):
            msg = self.custom_message or f"Condition not satisfied: {self.condition}"
            return [
                ValidationError(
                    field=", ".join(self._fields),
                    message=msg,
                    rule=self.name,
                )
            ]
        return []


class ListCardinalityRule(ValidationRule):
    """Validates list field cardinality (min/max items).

    Attributes:
        field: Name of the list field.
        min_items: Minimum number of items required (None = no minimum).
        max_items: Maximum number of items allowed (None = no maximum).
        rule_name: Name for this specific rule instance.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        field: str,
        min_items: int | None = None,
        max_items: int | None = None,
        rule_name: str = "list_cardinality",
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            field: Name of the list field.
            min_items: Minimum number of items required.
            max_items: Maximum number of items allowed.
            rule_name: Name for this rule instance.
            message: Optional custom error message.
        """
        self.field = field
        self.min_items = min_items
        self.max_items = max_items
        self.rule_name = rule_name
        self.custom_message = message

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return self.rule_name

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate list cardinality.

        Args:
            data: Dictionary containing the list field.

        Returns:
            List of errors if cardinality constraints violated.
        """
        value = data.get(self.field)
        errors: list[ValidationError] = []

        # Treat None or missing as empty list for min_items check
        if value is None:
            value = []

        if not isinstance(value, list):
            return errors

        count = len(value)

        if self.min_items is not None and count < self.min_items:
            msg = (
                self.custom_message
                or f"'{self.field}' must have at least {self.min_items} item(s), but has {count}"
            )
            errors.append(
                ValidationError(
                    field=self.field,
                    message=msg,
                    rule=self.name,
                )
            )

        if self.max_items is not None and count > self.max_items:
            msg = (
                self.custom_message
                or f"'{self.field}' must have at most {self.max_items} item(s), but has {count}"
            )
            errors.append(
                ValidationError(
                    field=self.field,
                    message=msg,
                    rule=self.name,
                )
            )

        return errors


class CoordinatePairRule(ValidationRule):
    """Validates that latitude and longitude are provided together.

    Attributes:
        lat_field: Name of the latitude field.
        lon_field: Name of the longitude field.
        rule_name: Name for this specific rule instance.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        lat_field: str = "latitude",
        lon_field: str = "longitude",
        rule_name: str = "coordinate_pair",
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            lat_field: Name of the latitude field.
            lon_field: Name of the longitude field.
            rule_name: Name for this rule instance.
            message: Optional custom error message.
        """
        self.lat_field = lat_field
        self.lon_field = lon_field
        self.rule_name = rule_name
        self.custom_message = message

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return self.rule_name

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate lat/lon are both present or both absent.

        Args:
            data: Dictionary to validate.

        Returns:
            List with error if only one coordinate provided.
        """
        has_lat = has_value(data, self.lat_field)
        has_lon = has_value(data, self.lon_field)

        if has_lat != has_lon:
            missing = self.lon_field if has_lat else self.lat_field
            present = self.lat_field if has_lat else self.lon_field
            msg = (
                self.custom_message
                or f"'{missing}' is required when '{present}' is provided"
            )
            return [
                ValidationError(
                    field=missing,
                    message=msg,
                    rule=self.name,
                )
            ]
        return []


class UniquenessRule(ValidationRule):
    """Detects duplicate field values across calls to a single rule instance.

    The rule accumulates values it has seen in ``_seen_values`` and reports an
    error when a value recurs. Detection therefore spans only the sequence of
    records passed to the *same* instance; it does not span records validated by
    different instances. ``ValidationEngine`` (and ``DatasetValidator``, which
    builds a fresh engine per entity node) constructs a new instance per record,
    so within those callers each invocation sees exactly one value and no
    duplicate is ever flagged.

    Dataset-wide cross-record identifier uniqueness and reference integrity are
    enforced separately by ``DatasetValidator`` via ``IdRegistry``, not by this
    rule. This rule is useful only to callers that deliberately reuse one
    instance across a sibling collection and call :meth:`reset` between scopes.

    Attributes:
        field: Name of the field to check for uniqueness.
        scope: Label for the intended uniqueness scope, used only in messages.
        rule_name: Name for this specific rule instance.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        field: str,
        scope: str = "parent",
        rule_name: str = "uniqueness",
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            field: Name of the field to check.
            scope: Uniqueness scope ("parent" or "global").
            rule_name: Name for this rule instance.
            message: Optional custom error message.
        """
        self.field = field
        self.scope = scope
        self.rule_name = rule_name
        self.custom_message = message
        self._seen_values: set[str] = set()

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return self.rule_name

    def reset(self: Self) -> None:
        """Clear accumulated values so the instance can be reused for a new scope.

        Callers that reuse a single instance across a sibling collection call
        this between scopes. The validation engine constructs a fresh instance
        per record and never calls it.
        """
        self._seen_values.clear()

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Report an error if this field's value was already seen by this instance.

        The check is stateful across calls to the same instance; the first
        occurrence of a value passes and subsequent occurrences fail.

        Args:
            data: Dictionary to validate.

        Returns:
            List with one error if the value duplicates a previously seen value
            on this instance, otherwise an empty list.
        """
        value = data.get(self.field)

        # Skip if field is missing or None
        if value is None:
            return []

        # Convert to string for consistent comparison
        str_value = str(value)

        if str_value in self._seen_values:
            msg = (
                self.custom_message
                or f"Value '{value}' is not unique within {self.scope}"
            )
            return [
                ValidationError(
                    field=self.field,
                    message=msg,
                    rule=self.name,
                )
            ]

        self._seen_values.add(str_value)
        return []


__all__ = [
    "ConditionalRule",
    "CoordinatePairRule",
    "DateRangeRule",
    "EntityReferenceRule",
    "ListCardinalityRule",
    "RequiredFieldsRule",
    "UniqueIdPatternRule",
    "UniquenessRule",
]
