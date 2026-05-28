"""Public API schema types for metaseed.

This module provides clean domain objects for schema introspection.
These types provide a stable public interface that is decoupled from
internal implementation details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldInfo:
    """Information about a single field in an entity schema.

    Provides a clean, immutable representation of field metadata
    for schema introspection.

    Attributes:
        name: Field name (snake_case).
        type: Field type (e.g., "string", "integer", "list").
        required: Whether the field is required.
        description: Human-readable description.
        ontology_term: Optional ontology term reference.
        items: For list/entity types, the type of items.
        constraints: Optional validation constraints dict.
        reference: Entity.field reference for integrity validation.
    """

    name: str
    type: str
    required: bool
    description: str = ""
    ontology_term: str | None = None
    items: str | None = None
    constraints: dict[str, Any] | None = None
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class EntitySchema:
    """Schema information for an entity type.

    Provides a clean, immutable representation of entity schema
    for introspection and documentation.

    Attributes:
        name: Entity name (PascalCase).
        description: Human-readable description.
        ontology_term: Optional ontology term reference.
        fields: List of field information objects.
        required_fields: List of required field names.
        optional_fields: List of optional field names.
    """

    name: str
    description: str
    ontology_term: str | None
    fields: tuple[FieldInfo, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]

    @property
    def all_field_names(self) -> tuple[str, ...]:
        """Get all field names."""
        return tuple(f.name for f in self.fields)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation issue.

    Attributes:
        field: Field path where the issue occurred.
        message: Human-readable error message.
        rule: Rule that triggered the issue.
    """

    field: str
    message: str
    rule: str


@dataclass(slots=True)
class ValidationResult:
    """Result of entity or dataset validation.

    Provides a structured representation of validation outcomes
    with helper methods for common checks.

    Attributes:
        valid: Whether validation passed.
        issues: List of validation issues (empty if valid).
    """

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @classmethod
    def success(cls) -> ValidationResult:
        """Create a successful validation result."""
        return cls(valid=True, issues=[])

    @classmethod
    def failure(cls, issues: list[ValidationIssue]) -> ValidationResult:
        """Create a failed validation result.

        Args:
            issues: List of validation issues.

        Returns:
            ValidationResult with valid=False.
        """
        return cls(valid=False, issues=issues)

    def __bool__(self) -> bool:
        """Return True if validation passed."""
        return self.valid

    @property
    def error_count(self) -> int:
        """Number of validation issues."""
        return len(self.issues)

    def get_field_errors(self, field: str) -> list[ValidationIssue]:
        """Get all issues for a specific field.

        Args:
            field: Field name to filter by.

        Returns:
            List of issues for the specified field.
        """
        return [issue for issue in self.issues if issue.field == field]
