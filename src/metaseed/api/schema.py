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
        example: Optional illustrative value (#98).
        options: Optional allowed values (controlled vocabulary), falling back to
            ``constraints.enum`` when the field declares no explicit options (#98).
        unit: Optional expected unit (#98).
        label: Optional human-readable label distinct from ``name`` (#98).
        tier: Optional advisory completeness tier
            ("required"/"recommended"/"optional") (#98).
    """

    name: str
    type: str
    required: bool
    description: str = ""
    ontology_term: str | None = None
    items: str | None = None
    constraints: dict[str, Any] | None = None
    example: str | int | float | bool | list[Any] | None = None
    options: list[str] | None = None
    unit: str | None = None
    label: str | None = None
    tier: str | None = None


@dataclass(frozen=True, slots=True)
class EntitySchema:
    """Schema information for an entity type.

    Provides a clean, immutable representation of entity schema
    for introspection and documentation.

    Attributes:
        name: Entity name (PascalCase).
        description: Human-readable description.
        ontology_term: Optional ontology term reference.
        fields: Tuple of field information objects.
        required_fields: Tuple of required field names.
        optional_fields: Tuple of optional field names.
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
        field: Name of the field where the issue occurred (bare, e.g.
            ``"latitude"``).
        message: Human-readable error message.
        rule: Rule that triggered the issue.
        entity_id: Id of the entity instance the issue belongs to, when known.
            Lets a caller identify which instance is at fault without encoding it
            into ``field``.
        kind: What the issue claims — ``"value"`` (wrong now and later) or
            ``"completeness"`` (absent or insufficient, normal mid-entry). A
            consumer enforcing a specification blocks on the first and reports
            the second; the split was computed by the validators and then
            discarded here, so every API consumer saw everything as blocking.
    """

    field: str
    message: str
    rule: str
    entity_id: str | None = None
    kind: str = "value"


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
