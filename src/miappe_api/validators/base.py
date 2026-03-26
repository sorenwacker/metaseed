"""Base classes for validation.

This module defines the base validation rule interface and error types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Self


@dataclass
class ValidationError:
    """Represents a validation error.

    Attributes:
        field: Name of the field that failed validation.
        message: Human-readable error message.
        rule: Name of the rule that generated the error.
    """

    field: str
    message: str
    rule: str

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
