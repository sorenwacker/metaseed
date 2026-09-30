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
        ambiguously-typed field, and per-child validation is unaffected. Each
        child now goes into the field it was recorded in (ADR 006).

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

        for child in node.children:
            # The field the child was recorded in (ADR 006).
            target_field = child.parent_field
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

    def _nested_document(self: Self, node: Any) -> dict[str, Any]:
        """A node's data with its whole subtree embedded, each record naming its node.

        The document ``check`` reads from a file, built from the store: children
        sit in the fields that hold them (ADR 006) at every depth, and every
        record carries ``_node_id`` so the dataset-level passes can say which
        node an error belongs to. Built once per root for those passes;
        :meth:`_data_with_children` stays one level deep for the per-entity ones.

        Args:
            node: The root of the subtree.

        Returns:
            The nested JSON document.
        """
        data = self._get_instance_data(node.instance)
        data["_node_id"] = node.id
        for child in node.children:
            target_field = child.parent_field
            if target_field is None:
                continue
            child_data = self._nested_document(child)
            existing = data.get(target_field)
            if isinstance(existing, list):
                existing.append(child_data)
            else:
                data[target_field] = child_data
        return data

    def _supplied_specs(self: Self, entity_type: str) -> dict[str, Any]:
        """The specs this client was composed with, for the validator to use.

        Empty for a client built by profile name, which leaves the validator
        resolving as before. A client built from a supplied spec has no profile
        on disk to resolve, so passing what it holds is the only way its
        entities can be validated at all rather than reported unknown.
        """
        profile_spec = getattr(self._facade, "_spec", None)
        if profile_spec is None:
            return {}
        helper = getattr(self._facade, entity_type, None)
        entity_spec = getattr(helper, "spec", None)
        if entity_spec is None:
            return {}
        return {"entity_spec": entity_spec, "profile_spec": profile_spec}

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
                **self._supplied_specs(node.entity_type),
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

        roots = self._facade.get_roots()
        for root in roots:
            validate_node(root)

        # The dataset-level passes -- reference integrity, declared uniqueness,
        # reference cycles -- need every record before judging one, so they are
        # the dataset validator's, run over the same nested documents ``check``
        # reads from a file. Skipped here, a reference to a record that does not
        # exist went unreported through every consumer built on validate().
        if roots:
            from metaseed.utils.text import to_snake_case
            from metaseed.validators import DatasetValidator

            validator = DatasetValidator(
                self._facade.profile,
                self._facade.version,
                profile_spec=self._facade.profile_spec,
            )
            records = [
                (self._nested_document(root), to_snake_case(root.entity_type))
                for root in roots
            ]
            for err in validator.validate_records(records).errors:
                all_issues.append(
                    ValidationIssue(
                        # Bare name, as every other issue: the record is named
                        # by entity_id, not encoded into the field path.
                        field=err.field.rsplit(".", 1)[-1],
                        message=err.message,
                        rule=err.rule,
                        entity_id=err.entity_id,
                        kind=err.kind.value,
                    )
                )

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
            **self._supplied_specs(node.entity_type),
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
