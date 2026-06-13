"""Validation mixin for MetaseedClient.

Provides methods for validating entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from metaseed.api.errors import EntityNotFoundError
from metaseed.api.schema import ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade


class ValidationMixin:
    """Mixin providing validation capabilities for MetaseedClient."""

    _facade: ProfileFacade

    def validate(self: Self) -> ValidationResult:
        """Validate all entities.

        Runs validation on all entities in the store.

        Returns:
            ValidationResult with any issues found.
        """
        from metaseed.validators import validate_entity

        all_issues: list[ValidationIssue] = []

        def validate_node(node: Any) -> None:
            data = self._get_instance_data(node.instance)
            if not data:
                return

            errors = validate_entity(
                data,
                entity_type=node.entity_type,
                profile=self._facade.profile,
                version=self._facade.version,
            )

            for err in errors:
                all_issues.append(
                    ValidationIssue(
                        field=f"{node.id}.{err.field}",
                        message=err.message,
                        rule=err.rule,
                    )
                )

            for child in node.children:
                validate_node(child)

        for root in self._facade.get_roots():
            validate_node(root)

        if all_issues:
            return ValidationResult.failure(all_issues)
        return ValidationResult.success()

    def validate_entity(self: Self, entity_id: str) -> ValidationResult:
        """Validate a specific entity.

        Args:
            entity_id: ID of the entity to validate.

        Returns:
            ValidationResult for the entity.

        Raises:
            EntityNotFoundError: If entity not found.
        """
        from metaseed.validators import validate_entity as validate_fn

        node = self._facade.get_entity(entity_id)
        if node is None:
            raise EntityNotFoundError(entity_id)

        data = self._get_instance_data(node.instance)

        errors = validate_fn(
            data,
            entity_type=node.entity_type,
            profile=self._facade.profile,
            version=self._facade.version,
        )

        issues = [
            ValidationIssue(field=err.field, message=err.message, rule=err.rule)
            for err in errors
        ]

        if issues:
            return ValidationResult.failure(issues)
        return ValidationResult.success()
