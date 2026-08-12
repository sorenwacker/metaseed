"""Base classes for validation.

This module defines the base validation rule interface and error types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self


def has_value(data: dict[str, Any], field: str) -> bool:
    """Check if a field has a non-empty value.

    Args:
        data: Dictionary to check.
        field: Field name to check.

    Returns:
        True if the field exists and has a non-empty value.
    """
    value = data.get(field)
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


@dataclass
class ValidationCheck:
    """Represents an individual validation check result.

    Tracks pass/fail status for each validation check performed,
    allowing detailed reporting of what was validated.

    Attributes:
        field: Name of the field being validated.
        check: Type of check performed (e.g., "required", "pattern", "min_length").
        passed: Whether the check passed.
        message: Error message if failed, None if passed.
    """

    field: str
    check: str
    passed: bool
    message: str | None = None

    def __str__(self: Self) -> str:
        """Return string representation of the check."""
        status = "passed" if self.passed else "failed"
        if self.message:
            return f"{self.field}.{self.check}: {status} - {self.message}"
        return f"{self.field}.{self.check}: {status}"


class Kind(StrEnum):
    """What a validation error is claiming.

    Two claims are routinely conflated, and conflating them makes a
    specification unenforceable. "This value is wrong" is about something the
    person supplied: it is true now and stays true, and the work cannot be
    called correct while it holds. "This is not finished" is about something
    absent: a list with fewer than three entries, a required field not filled
    in yet. It is true of every dataset at the moment it is created.

    Enforced identically, the second blocks the first save of a Study whose
    profile requires three design descriptors — no value the person types can
    clear it, because the rule is about a list they have not reached yet
    (#246). Its mirror is #217: absence going unchecked entirely.

    Consumers were left to draw this line themselves; drawing it here means one
    answer rather than one per application.
    """

    VALUE = "value"
    COMPLETENESS = "completeness"


@dataclass
class ValidationError:
    """Represents a validation error.

    Attributes:
        field: Name of the field that failed validation.
        message: Human-readable error message.
        rule: Name of the rule that generated the error.
        kind: Whether this says a supplied value is wrong, or that something is
            missing. Defaults to :attr:`Kind.VALUE` — the stricter reading, so
            a rule that has not been classified is never quietly downgraded.
    """

    field: str
    message: str
    rule: str
    kind: Kind = Kind.VALUE

    @property
    def blocks(self: Self) -> bool:
        """Whether this should stop the work from being called correct.

        A completeness error does not: it describes a dataset that is not
        finished, which is the normal state of one being written.
        """
        return self.kind is Kind.VALUE

    def __str__(self: Self) -> str:
        """Return string representation of the error."""
        return f"{self.field}: {self.message} (rule: {self.rule})"


class ValidationRule(ABC):
    """Base class for validation rules.

    Validation rules check specific conditions on data and return
    a list of errors if validation fails.
    """

    @property
    @abstractmethod
    def name(self: Self) -> str:
        """Return the name of this rule."""
        ...

    @abstractmethod
    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Validate data against this rule.

        Args:
            data: Dictionary of field names to values.

        Returns:
            List of validation errors. Empty list if validation passes.
        """
        ...
