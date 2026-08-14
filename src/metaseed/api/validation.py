"""Validation mixin for MetaseedClient.

Provides methods for validating entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from metaseed.api.base import InstanceDataMixin
from metaseed.api.errors import EntityNotFoundError
from metaseed.api.schema import ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade


class ValidationMixin(InstanceDataMixin):
    """Mixin providing validation capabilities for MetaseedClient."""

    _facade: ProfileFacade

    def _data_with_children(self: Self, node: Any) -> dict[str, Any]:
        """Return a node's data with its child nodes embedded in nested fields.

        The client stores children as sibling nodes, so a parent's nested list
        field is empty on its own instance even when children exist. List
        cardinality rules (``min_items``/``max_items``) would then always report
        the parent as invalid. Re-attaching each child into the matching nested
        field lets those rules validate against the real subtree, while the
        child's own content is still validated when the traversal reaches it.

        A child is matched to a field by entity type. When a parent nests the
        same type in more than one field, all such children land in the first
        of those fields; no shipped cardinality rule targets an
        ambiguously-typed field, and per-child validation is unaffected. Which
        field a child truly belongs to is not recorded today (see issue #137).

        Args:
            node: The entity node whose data to reconstruct.

        Returns:
            The node's JSON data dict, with children embedded in nested fields.
        """
        data = self._get_instance_data(node.instance)
        if not node.children:
            return data

        helper = self._facade.get_helper(node.entity_type)
        if helper is None:
            return data

        # entity type -> first nested field of that type
        field_for_type: dict[str, str] = {}
        for field_name, entity_type in helper.nested_fields.items():
            field_for_type.setdefault(entity_type, field_name)

        for child in node.children:
            target_field = field_for_type.get(child.entity_type)
            if target_field is None:
                continue
            child_data = self._get_instance_data(child.instance)
            existing = data.get(target_field)
            if isinstance(existing, list):
                existing.append(child_data)
            else:
                # A single (non-list) nested entity field, empty on the parent.
                data[target_field] = child_data
        return data

    def validate(self: Self) -> ValidationResult:
        """Validate all entities.

        Runs validation on all entities in the store.

        Returns:
            ValidationResult with any issues found.
        """
        from metaseed.validators import validate_entity

        all_issues: list[ValidationIssue] = []

        def validate_node(node: Any) -> None:
            data = self._data_with_children(node)
            # No `if data:` guard: an entity whose dump is {} (created empty
            # with skip_validation) still has required fields to report —
            # skipping it made validate() call an entity valid that
            # validate_entity() on the same node calls invalid.
            errors = validate_entity(
                data,
                entity_type=node.entity_type,
                profile=self._facade.profile,
                version=self._facade.version,
            )

            for err in errors:
                all_issues.append(
                    ValidationIssue(
                        field=err.field,
                        message=err.message,
                        rule=err.rule,
                        entity_id=node.id,
                        kind=err.kind.value,
                    )
                )

            # Always descend; an empty node must not hide its subtree.
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

        data = self._data_with_children(node)

        errors = validate_fn(
            data,
            entity_type=node.entity_type,
            profile=self._facade.profile,
            version=self._facade.version,
        )

        issues = [
            ValidationIssue(
                field=err.field,
                message=err.message,
                rule=err.rule,
                entity_id=node.id,
                kind=err.kind.value,
            )
            for err in errors
        ]

        if issues:
            return ValidationResult.failure(issues)
        return ValidationResult.success()
