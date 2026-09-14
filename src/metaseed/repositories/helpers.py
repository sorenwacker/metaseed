"""Shared helper functions for entity repositories.

These utilities are used by both FileEntityRepository and MemoryEntityRepository
to handle common operations like finding parent references and deriving labels.
"""

from __future__ import annotations

import copy
import datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import AnyUrl

if TYPE_CHECKING:
    from metaseed.facade import EntityHelper


def find_parent_ref_field(helper: Any, parent_type: str) -> str | None:
    """Find field on child entity that references parent type.

    Uses the spec's reference field definitions.

    Args:
        helper: Entity helper with reference_fields property.
        parent_type: Parent entity type name.

    Returns:
        Field name if found, None otherwise.
    """
    if hasattr(helper, "reference_fields"):
        for field_name, (target_type, _target_field) in helper.reference_fields.items():
            if target_type == parent_type:
                return cast("str", field_name)
    return None


def get_identifier(
    data: dict[str, Any], helper: EntityHelper | None = None
) -> str | None:
    """Get identifier value from entity data.

    Uses the helper's identifier field (the first non-reference field in the
    spec) when a helper is given.

    Args:
        data: Entity data dictionary.
        helper: EntityHelper for spec-based lookup.

    Returns:
        Identifier string if found, None otherwise.
    """
    if helper and helper.identifier_field:
        value = data.get(helper.identifier_field)
        if value:
            return str(value)
    return None


def get_identifier_from_instance(
    instance: Any, helper: EntityHelper | None = None
) -> str | None:
    """Get identifier from a Pydantic model instance.

    Args:
        instance: Pydantic model instance.
        helper: Optional EntityHelper for spec-based lookup.

    Returns:
        Identifier string if found, None otherwise.
    """
    if not instance or not hasattr(instance, "model_dump"):
        return None
    data = instance.model_dump(exclude_none=True)
    return get_identifier(data, helper)


def _label_text(value: Any) -> str | None:
    """The text of a value that can stand on its own as a display label.

    Validation turns ``uri``, ``date`` and ``datetime`` values into URL and
    date objects; they label as their text, so an entity labels the same
    before and after it is validated. Nested entities (dicts, Pydantic models)
    and collections stringify into unreadable dumps and give no label.
    """
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, datetime.date):  # also covers datetime.datetime
        return value.isoformat()
    if isinstance(value, AnyUrl):
        return str(value)
    return None


def derive_label(entity_type: str, data: dict[str, Any], spec: Any = None) -> str:
    """Derive a display label from entity data.

    A field explicitly marked ``is_label`` in the spec wins; otherwise the
    convention is the first field. Declaring ``is_label`` lets entities whose
    first field is a parent reference (e.g. isa Source's ``study_id``) show a
    meaningful label instead of the reference.

    Args:
        entity_type: Type of entity.
        data: Entity data dictionary.
        spec: EntityDefSpec with field definitions.

    Returns:
        Derived label string.
    """
    if spec and hasattr(spec, "fields") and spec.fields:
        declared = next(
            (f.name for f in spec.fields if getattr(f, "is_label", None)), None
        )
        label_field = declared or spec.fields[0].name
        value = data.get(label_field)
        # A declared list (e.g. one name per language) labels by its first
        # entry; an undeclared first field that is a list is not a label.
        if declared and isinstance(value, list) and value:
            value = value[0]
        if value:
            text = _label_text(value)
            if text is not None:
                return text[:50]
            # The chosen field holds a nested entity (e.g. isa
            # ProtocolParameter's entity-typed ``parameter_name``); stringifying
            # it yields a dict dump, not a label. Fall through to the first
            # single value instead, skipping references — they identify the
            # parent, not this entity.
            for f in spec.fields:
                if getattr(f, "reference", None) or f.name == label_field:
                    continue
                candidate = data.get(f.name)
                text = _label_text(candidate) if candidate else None
                if text is not None:
                    return text[:50]

    return f"New {entity_type}"


def update_parent_reference(
    facade: Any,
    parent_data: dict[str, Any],
    parent_type: str,
    child_data: dict[str, Any],
    child_type: str,
    child_id: str,
    parent_field: str | None = None,
) -> str | None:
    """Update parent's reference field to include child.

    Adds the child's identifier to ``parent_field``, or to the parent's single
    field for the child's type when no field is named (ADR 006).

    Args:
        facade: ProfileFacade instance.
        parent_data: Parent entity data (will be modified).
        parent_type: Parent entity type name.
        child_data: Child entity data.
        child_type: Child entity type name.
        child_id: Child's node ID (fallback if no identifier).
        parent_field: The parent field the child goes into.

    Returns:
        Name of updated field, or None if no matching field found.

    Raises:
        ValueError: If the field is ambiguous or does not hold the child's type.
    """
    from metaseed.facade.linking import (
        NO_CHANGE,
        choose_parent_field,
        linked_reference_value,
    )

    parent_helper = getattr(facade, parent_type, None)
    if not parent_helper:
        return None

    target_field = choose_parent_field(parent_helper, child_type, parent_field)
    if not target_field:
        return None

    # Get child's identifier using spec
    child_helper = getattr(facade, child_type, None)
    child_ref = get_identifier(child_data, child_helper) or child_id

    # The decision — including the LIST-vs-ENTITY shape rule — is owned by
    # facade.linking (ADR 005); this applier only lands it on the data dict.
    new_value = linked_reference_value(
        parent_helper, target_field, parent_data.get(target_field), child_ref
    )
    if new_value is not NO_CHANGE:
        parent_data[target_field] = new_value

    return target_field


def remove_parent_reference(
    facade: Any,
    parent_data: dict[str, Any],
    parent_type: str,
    child_data: dict[str, Any],
    child_type: str,
    child_id: str,
    parent_field: str | None = None,
) -> str | None:
    """Undo :func:`update_parent_reference` when the child is deleted.

    ``create`` writes the child's identifier into the parent's nested
    reference field; a delete that leaves it there hands every export and
    reload a reference to a record that no longer exists.

    Returns:
        Name of the field the reference was removed from, or None.
    """
    from metaseed.facade.linking import (
        NO_CHANGE,
        field_naming_child,
        unlinked_reference_value,
    )

    parent_helper = getattr(facade, parent_type, None)
    if not parent_helper:
        return None

    child_helper = getattr(facade, child_type, None)
    child_ref = get_identifier(child_data, child_helper) or child_id

    target_field = parent_field or field_naming_child(
        parent_helper, parent_data, child_type, {str(child_ref)}
    )
    if not target_field:
        return None

    new_value = unlinked_reference_value(
        parent_helper, target_field, parent_data.get(target_field), {child_ref}
    )
    if new_value is not NO_CHANGE:
        parent_data[target_field] = new_value
    return target_field


def normalize_reference_fields(
    data: dict[str, Any], helper: EntityHelper, facade: Any = None
) -> dict[str, Any]:
    """Normalize reference fields in entity data to store IDs instead of embedded objects.

    When an MCP agent creates entities, it may pass embedded objects for reference
    fields (e.g., derives_from: [{name: "SOURCE-001", ...}]). This function
    normalizes such fields to store just the identifiers (e.g., ["SOURCE-001"]).

    Args:
        data: Entity data dictionary (will NOT be modified in-place).
        helper: EntityHelper for the entity type.
        facade: Optional ProfileFacade for looking up target entity helpers.

    Returns:
        New dictionary with normalized reference fields.
    """
    # Make a shallow copy to avoid modifying input
    result = copy.copy(data)

    # Get fields that reference other entities
    nested_fields = helper.nested_fields

    for field_name, target_type in nested_fields.items():
        if field_name not in result:
            continue

        value = result[field_name]
        if value is None:
            continue

        # Get target entity helper for identifier lookup
        target_helper = getattr(facade, target_type, None) if facade else None

        # Handle list fields
        if isinstance(value, list):
            normalized_list = []
            for item in value:
                if isinstance(item, dict):
                    # Extract identifier from embedded object
                    item_id = get_identifier(item, target_helper)
                    if item_id:
                        normalized_list.append(item_id)
                elif isinstance(item, str):
                    # Already an ID
                    normalized_list.append(item)
            if normalized_list:
                result[field_name] = normalized_list

        # Handle single entity fields
        elif isinstance(value, dict):
            # Extract identifier from embedded object
            item_id = get_identifier(value, target_helper)
            if item_id:
                result[field_name] = item_id

    return result
