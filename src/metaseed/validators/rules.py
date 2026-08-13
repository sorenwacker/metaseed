"""Concrete validation rules.

This module provides common validation rules for MIAPPE entities.
"""

import datetime
import re
from typing import Any, Self

import regex

from metaseed.specs.predicates import Predicate, render_predicate
from metaseed.validators.base import Kind, ValidationError, ValidationRule, has_value
from metaseed.validators.predicates import PredicateError, evaluate

# Ceiling on evaluating a single user-supplied pattern against one value. Patterns
# come from user-authored specs and are matched against user data, so a
# catastrophic-backtracking pattern (e.g. ``(a+)+$``) could otherwise hang the
# process for minutes on a short input. The ``regex`` module enforces this bound
# mid-match (stdlib ``re`` cannot be interrupted); on timeout we fail the value
# closed rather than let it block. One second is far above any legitimate match.
_PATTERN_MATCH_TIMEOUT_SECONDS = 1.0


def _matches_within_timeout(pattern: "regex.Pattern[str]", value: str) -> bool:
    """Return whether ``value`` matches ``pattern``, treating a timeout as no match.

    Args:
        pattern: A compiled ``regex`` pattern.
        value: The string to test.

    Returns:
        True if the value matches; False if it does not or the match timed out.
    """
    try:
        return pattern.match(value, timeout=_PATTERN_MATCH_TIMEOUT_SECONDS) is not None
    except TimeoutError:
        return False


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

        # A successful parse (no errors) guarantees both dates are non-None;
        # this guard narrows the Optional for the comparison below.
        if start is None or end is None:
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


class NumericRangeRule(ValidationRule):
    """Validates that the upper end of a numeric range is not below the lower.

    The sibling of :class:`DateRangeRule` for quantities: a depth, an
    elevation, a temperature span. Darwin Core declares
    ``maximumDepthInMeters >= minimumDepthInMeters``, which was checked by the
    date validator and reported two floats as "not a valid date", so both
    fields could never be populated at once (#246).

    Attributes:
        lower_field: Name of the field holding the lower bound.
        upper_field: Name of the field holding the upper bound.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        lower_field: str,
        upper_field: str,
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            lower_field: Name of the lower-bound field.
            upper_field: Name of the upper-bound field.
            message: Optional custom error message.
        """
        self.lower_field = lower_field
        self.upper_field = upper_field
        self.custom_message = message

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return "numeric_range"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate that the upper bound is not below the lower bound.

        Args:
            data: Dictionary with both bound fields.

        Returns:
            One error if the range is inverted, or if a value is not a number.
            Empty when either bound is absent: whether a bound is required is a
            different question, with its own rule.
        """
        lower_raw = data.get(self.lower_field)
        upper_raw = data.get(self.upper_field)

        if lower_raw is None or upper_raw is None:
            return []
        if lower_raw == "" or upper_raw == "":
            return []

        errors: list[ValidationError] = []
        lower = self._parse_number(lower_raw, self.lower_field, errors)
        upper = self._parse_number(upper_raw, self.upper_field, errors)
        if errors or lower is None or upper is None:
            return errors

        if upper < lower:
            msg = self.custom_message or (
                f"{self.upper_field} ({upper}) must not be below "
                f"{self.lower_field} ({lower})"
            )
            return [
                ValidationError(field=self.upper_field, message=msg, rule=self.name)
            ]
        return []

    def _parse_number(
        self: Self, value: Any, field: str, errors: list[ValidationError]
    ) -> float | None:
        """Read a number, recording an error rather than raising.

        The engine runs against raw, un-coerced data, so a value that is not a
        number is a validation error here rather than a crash mid-run.
        """
        if isinstance(value, bool):
            # A bool is an int in Python and never a measurement.
            errors.append(
                ValidationError(
                    field=field,
                    message=f"Field '{field}' is not a number: {value}",
                    rule=self.name,
                )
            )
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            errors.append(
                ValidationError(
                    field=field,
                    message=f"Field '{field}' is not a number: {value}",
                    rule=self.name,
                )
            )
            return None


class RequiredFieldsRule(ValidationRule):
    """Reports required fields that are absent or empty.

    Building an entity does not enforce requiredness, so this rule is the only
    thing that tells anyone a required value is missing. Removing it would not
    loosen validation; it would make the gap invisible.

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
                        # Absence, not a wrong value: true of every dataset the
                        # moment it is created, and no value the person types
                        # while filling in the rest can clear it.
                        kind=Kind.COMPLETENESS,
                    )
                )
        return errors


class UniqueIdPatternRule(ValidationRule):
    """Validates that unique IDs match the expected pattern.

    The default shape — alphanumerics, underscores and hyphens — is MIAPPE's,
    and applies only where a profile states nothing about its own identifiers.
    A profile that declares a pattern for the field has that pattern enforced
    instead; see ``engine._identifier_rule``. An identifier is not universally
    shaped: a DiSSCo specimen is identified by a DOI.

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
        self.pattern = regex.compile(pattern or self.DEFAULT_PATTERN)

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

        if not _matches_within_timeout(self.pattern, value):
            return [
                ValidationError(
                    field=self.field,
                    message=f"Field '{self.field}' contains invalid characters. "
                    "Only alphanumeric characters, underscores, and hyphens allowed.",
                    rule=self.name,
                )
            ]
        return []


class PatternRule(ValidationRule):
    """Validates that a field's value matches a regex pattern.

    Used for rule-level ``pattern`` constraints on field types the model factory
    cannot enforce with a Pydantic pattern — notably ``uri`` (which maps to
    ``AnyUrl``, on which a regex constraint is invalid) and ``ontology_term``.
    String-typed patterns are already merged onto the field and enforced by
    Pydantic (see ``loader._merge_rule_constraints_into_fields``); this rule
    covers the rest. An absent/empty value passes — requiredness is a separate
    rule.
    """

    def __init__(self: Self, field: str, pattern: str, message: str | None = None):
        """Initialize the rule.

        Args:
            field: Name of the field to validate.
            pattern: Regex the value must match.
            message: Optional custom error message.
        """
        self.field = field
        self.pattern = regex.compile(pattern)
        self._message = message

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return "pattern"

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate the field value matches the pattern (str-coerced)."""
        value = data.get(self.field)
        if value in (None, ""):
            return []
        if not _matches_within_timeout(self.pattern, str(value)):
            return [
                ValidationError(
                    field=self.field,
                    message=self._message
                    or f"Field '{self.field}' does not match the required pattern",
                    rule=self.name,
                )
            ]
        return []


class ConditionalRequirementRule(ValidationRule):
    """Requires fields of a record when a predicate holds of that record.

    The legacy :class:`ConditionalRule` reads a condition string by asking
    whether each named field is *present*; it never reads a value, so
    "``cv_terms`` is required when ``data_type`` is Controlled Vocabulary" could
    not be written (#211). This is the value-dependent form: ``when`` is a
    predicate over the record's own fields and ``require`` names what it demands.

    The two are alternatives rather than layers -- a rule setting both ``when``
    and ``condition`` is rejected at profile load, since a precedence between
    them would be a rule nobody could remember.

    Attributes:
        when: The predicate deciding whether the requirement applies.
        require: Fields the record must carry when it does.
        rule_name: Name for this specific rule instance.
        custom_message: Optional custom error message.
    """

    def __init__(
        self: Self,
        when: Predicate,
        require: list[str],
        rule_name: str = "conditional_requirement",
        message: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            when: Predicate over the record's own fields.
            require: Fields required when the predicate holds.
            rule_name: Name for this rule instance.
            message: Optional custom error message.
        """
        self.when = when
        self.require = require
        self.rule_name = rule_name
        self.custom_message = message

    @property
    def name(self: Self) -> str:
        """Return the rule name."""
        return self.rule_name

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Report the required fields a record is missing.

        Args:
            data: The record.

        Returns:
            One error per missing field, or one error if the predicate could not
            be applied to this record at all.
        """
        try:
            applies = evaluate(self.when, data)
        except PredicateError as exc:
            return [
                ValidationError(field="", message=f"{self.name}: {exc}", rule=self.name)
            ]
        if not applies:
            return []

        reason = f"is required when {render_predicate(self.when)}"
        return [
            ValidationError(
                field=field,
                message=(
                    f"{self.custom_message} (field '{field}' {reason})"
                    if self.custom_message
                    else f"Field '{field}' {reason}"
                ),
                rule=self.name,
                # A field that is not filled in yet, exactly like any other
                # required field: reported, not blocking (#246).
                kind=Kind.COMPLETENESS,
            )
            for field in self.require
            if not has_value(data, field)
        ]


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
    """Validates list field cardinality (min/max items), optionally over a subset.

    With a ``where`` predicate the rule counts only the items it selects, which
    is what lets a constraint be written about *some* of a collection — "exactly
    one attribute is the display column" rather than "the list has one entry"
    (#211). The predicate reads each **item**; the rule already reaches one level
    down through ``field``, and the predicate adds no traversal of its own.

    Attributes:
        field: Name of the list field.
        min_items: Minimum number of items required (None = no minimum).
        max_items: Maximum number of items allowed (None = no maximum).
        rule_name: Name for this specific rule instance.
        custom_message: Optional custom error message.
        where: Predicate selecting which items count (None = all of them).
        label_field: Field of an item to name it by when reporting which items
            were counted. Resolved from the item entity's declared identity
            markers by the engine; ``None`` falls back to the index alone.
    """

    def __init__(
        self: Self,
        field: str,
        min_items: int | None = None,
        max_items: int | None = None,
        rule_name: str = "list_cardinality",
        message: str | None = None,
        where: Predicate | None = None,
        label_field: str | None = None,
    ) -> None:
        """Initialize the rule.

        Args:
            field: Name of the list field.
            min_items: Minimum number of items required.
            max_items: Maximum number of items allowed.
            rule_name: Name for this rule instance.
            message: Optional custom error message.
            where: Predicate selecting which items are counted.
            label_field: Field of an item to name it by in a message.
        """
        self.field = field
        self.min_items = min_items
        self.max_items = max_items
        self.rule_name = rule_name
        self.custom_message = message
        self.where = where
        self.label_field = label_field

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

        # Treat None or missing as empty list for min_items check
        if value is None:
            value = []

        if not isinstance(value, list):
            return []

        if self.where is None:
            return self._bound_errors(len(value), None, len(value))

        try:
            matched = self._matching(value)
        except PredicateError as exc:
            # Not swallowed into "nothing matched": that would leave the rule
            # quietly satisfied by a predicate that cannot be applied at all.
            return [
                ValidationError(
                    field=self.field,
                    message=f"{self.name}: {exc}",
                    rule=self.name,
                )
            ]
        return self._bound_errors(len(matched), matched, len(value))

    def _matching(self: Self, items: list[Any]) -> list[tuple[int, Any]]:
        """The items the predicate selects, with their positions.

        An item that is not a record has no fields to read, so it matches
        nothing. A ``where`` over a list of scalars is rejected at profile load;
        this only keeps a dataset that holds one from crashing the run.
        """
        assert self.where is not None
        return [
            (index, item)
            for index, item in enumerate(items)
            if isinstance(item, dict) and evaluate(self.where, item)
        ]

    def _bound_errors(
        self: Self,
        count: int,
        matched: list[tuple[int, Any]] | None,
        population: int,
    ) -> list[ValidationError]:
        """The errors the counted total produces against the declared bounds."""
        errors: list[ValidationError] = []
        if self.min_items is not None and count < self.min_items:
            errors.append(
                ValidationError(
                    field=self.field,
                    message=self._message(
                        "at least", self.min_items, count, matched, population
                    ),
                    rule=self.name,
                    # "Not enough yet" — a Study whose profile wants three
                    # design descriptors cannot be saved for the first time if
                    # this blocks (#246).
                    kind=Kind.COMPLETENESS,
                )
            )
        if self.max_items is not None and count > self.max_items:
            errors.append(
                ValidationError(
                    field=self.field,
                    message=self._message(
                        "at most", self.max_items, count, matched, population
                    ),
                    rule=self.name,
                )
            )
        return errors

    def _message(
        self: Self,
        direction: str,
        bound: int,
        count: int,
        matched: list[tuple[int, Any]] | None,
        population: int,
    ) -> str:
        """Render the failure.

        Unpredicated, this is the message it has always been. Predicated, it
        states what was counted and out of what: "expected exactly 1, found 0"
        is unactionable against 24 children when the reader cannot see which of
        them were counted or why.
        """
        if matched is None or self.where is None:
            return (
                self.custom_message
                or f"'{self.field}' must have {direction} {bound} item(s), but has {count}"
            )

        quantifier = (
            "exactly"
            if self.min_items is not None and self.min_items == self.max_items
            else direction
        )
        detail = (
            f"expected {quantifier} {bound} of {population} '{self.field}' to match "
            f"{render_predicate(self.where)}, found {count}"
        )
        if matched:
            detail += ": " + ", ".join(
                self._named(index, item) for index, item in matched
            )
        # A custom message on a predicated rule is prefixed rather than
        # substituted: replacing it would discard the only actionable part.
        return f"{self.custom_message} ({detail})" if self.custom_message else detail

    def _named(self: Self, index: int, item: Any) -> str:
        """One counted member, as ``attributes[3] 'Sample Name'``."""
        path = f"{self.field}[{index}]"
        label = item.get(self.label_field) if self.label_field else None
        return f"{path} '{label}'" if label else path


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


__all__ = [
    "ConditionalRule",
    "CoordinatePairRule",
    "DateRangeRule",
    "ListCardinalityRule",
    "NumericRangeRule",
    "PatternRule",
    "RequiredFieldsRule",
    "UniqueIdPatternRule",
]
