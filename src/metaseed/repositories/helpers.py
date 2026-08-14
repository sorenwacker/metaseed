"""Shared helper functions for entity repositories.

These utilities are used by both FileEntityRepository and MemoryEntityRepository
to handle common operations like finding parent references and deriving labels.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, cast

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


def _is_scalar(value: Any) -> bool:
    """True when a value can stand on its own as a display label.

    Nested entities (dicts, Pydantic models) and collections stringify into
    unreadable dumps, so they are never used as a label.
    """
    return isinstance(value, (str, int, float, bool))


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
        label_field = next(
            (f.name for f in spec.fields if getattr(f, "is_label", None)),
            spec.fields[0].name,
        )
        value = data.get(label_field)
        if value:
            if _is_scalar(value):
                return str(value)[:50]
            # The chosen field holds a nested entity (e.g. isa
            # ProtocolParameter's entity-typed ``parameter_name``); stringifying
            # it yields a dict dump, not a label. Fall through to the first
            # scalar instead, skipping references — they identify the parent,
            # not this entity.
            for f in spec.fields:
                if getattr(f, "reference", None) or f.name == label_field:
                    continue
                candidate = data.get(f.name)
                if candidate and _is_scalar(candidate):
                    return str(candidate)[:50]

    return f"New {entity_type}"


def update_parent_reference(
    facade: Any,
    parent_data: dict[str, Any],
    parent_type: str,
    child_data: dict[str, Any],
    child_type: str,
    child_id: str,
) -> str | None:
    """Update parent's reference field to include child.

    Finds the nested field on parent that references child's type
    and adds the child's identifier to that field.

    Args:
        facade: ProfileFacade instance.
        parent_data: Parent entity data (will be modified).
        parent_type: Parent entity type name.
        child_data: Child entity data.
        child_type: Child entity type name.
        child_id: Child's node ID (fallback if no identifier).

    Returns:
        Name of updated field, or None if no matching field found.
    """
    parent_helper = getattr(facade, parent_type, None)
    if not parent_helper:
        return None

    # Find which field on parent references the child's type
    nested_fields = parent_helper.nested_fields
    target_field = None
    for field_name, ref_type in nested_fields.items():
        if ref_type == child_type:
            target_field = field_name
            break

    if not target_field:
        return None

    # Get child's identifier using spec
    child_helper = getattr(facade, child_type, None)
    child_ref = get_identifier(child_data, child_helper) or child_id

    # An ENTITY-typed field holds exactly one scalar reference; coercing it
    # into a list silently corrupted its shape (entity fields are typed Any,
    # so no model ever caught it) and stacked children onto an
    # exactly-one-child field. The first child claims it; later children are
    # still parented through the tree, just not re-referenced here.
    if target_field in parent_helper.single_entity_fields:
        if not parent_data.get(target_field):
            parent_data[target_field] = child_ref
        return cast("str", target_field)

    refs = parent_data.get(target_field, [])
    if not isinstance(refs, list):
        refs = [refs] if refs else []

    if child_ref not in refs:
        refs.append(child_ref)
        parent_data[target_field] = refs

    return cast("str", target_field)


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
