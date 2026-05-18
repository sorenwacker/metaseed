"""Shared helper functions for entity repositories.

These utilities are used by both FileEntityRepository and AppStateAdapter
to handle common operations like finding parent references and deriving labels.
"""

from __future__ import annotations

from typing import Any

# Common field names for entity identification
IDENTIFIER_FIELDS = ["unique_id", "identifier", "name", "id", "filename"]

# Common field names for deriving labels
LABEL_FIELDS = ["title", "name", "unique_id", "identifier", "filename"]


def find_parent_ref_field(helper: Any, parent_type: str) -> str | None:
    """Find field on child entity that references parent type.

    Searches for common naming patterns like 'investigation_id',
    'study_identifier', etc.

    Args:
        helper: Entity helper with _spec attribute.
        parent_type: Parent entity type name.

    Returns:
        Field name if found, None otherwise.
    """
    parent_lower = parent_type.lower()
    patterns = [
        f"{parent_lower}_id",
        f"{parent_lower}_identifier",
        f"{parent_lower}_unique_id",
        parent_lower,
    ]

    for field in helper._spec.fields:
        if field.name.lower() in patterns:
            return field.name
    return None


def get_identifier(data: dict[str, Any]) -> str | None:
    """Get identifier value from entity data.

    Tries common identifier field names in order of preference.

    Args:
        data: Entity data dictionary.

    Returns:
        Identifier string if found, None otherwise.
    """
    for id_field in IDENTIFIER_FIELDS:
        if data.get(id_field):
            return str(data[id_field])
    return None


def get_identifier_from_instance(instance: Any) -> str | None:
    """Get identifier from a Pydantic model instance.

    Args:
        instance: Pydantic model instance.

    Returns:
        Identifier string if found, None otherwise.
    """
    if not instance or not hasattr(instance, "model_dump"):
        return None
    data = instance.model_dump(exclude_none=True)
    return get_identifier(data)


def derive_label(entity_type: str, data: dict[str, Any]) -> str:
    """Derive a display label from entity data.

    Tries common label fields, with special handling for Person entities.

    Args:
        entity_type: Type of entity.
        data: Entity data dictionary.

    Returns:
        Derived label string.
    """
    for key in LABEL_FIELDS:
        if data.get(key):
            return str(data[key])

    # Person special case: combine first and last name
    if data.get("first_name"):
        parts = [data.get("first_name", ""), data.get("last_name", "")]
        label = " ".join(p for p in parts if p).strip()
        if label:
            return label

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

    # Get child's identifier
    child_ref = get_identifier(child_data) or child_id

    # Get or create the list field
    refs = parent_data.get(target_field, [])
    if not isinstance(refs, list):
        refs = [refs] if refs else []

    # Add reference if not already present
    if child_ref not in refs:
        refs.append(child_ref)
        parent_data[target_field] = refs

    return target_field
