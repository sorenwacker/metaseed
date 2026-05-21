"""Shared helper functions for entity repositories.

These utilities are used by both FileEntityRepository and AppStateAdapter
to handle common operations like finding parent references and deriving labels.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.facade import EntityHelper

# Common field names for entity identification
IDENTIFIER_FIELDS = ["unique_id", "identifier", "name", "id", "alias", "accession", "filename"]

# Common field names for deriving labels (in preference order)
LABEL_FIELDS = [
    "title",
    "name",
    "display_name",
    "unique_id",
    "identifier",
    "alias",
    "accession",
    "id",
    "term",
    "filename",
]

# Entity-specific label field priorities
# These are checked before the generic LABEL_FIELDS
ENTITY_LABEL_FIELDS: dict[str, list[str]] = {
    "BiologicalMaterial": [
        "organism",
        "genus",
        "species",
        "infraspecific_name",
        "unique_id",
    ],
    "ObservedVariable": [
        "name",
        "trait",
        "unique_id",
    ],
    "Sample": [
        "description",
        "unique_id",
    ],
    "Event": [
        "type",
        "description",
    ],
}


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


def get_identifier(data: dict[str, Any], spec: Any = None) -> str | None:
    """Get identifier value from entity data.

    If spec has identifier_field defined, uses that first.
    Otherwise tries common identifier field names in order of preference.

    Args:
        data: Entity data dictionary.
        spec: Optional EntityDefSpec with identifier_field.

    Returns:
        Identifier string if found, None otherwise.
    """
    # First priority: spec-defined identifier_field
    if spec and hasattr(spec, "identifier_field") and spec.identifier_field:
        if data.get(spec.identifier_field):
            return str(data[spec.identifier_field])

    # Fallback to common identifier fields
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


def derive_label(entity_type: str, data: dict[str, Any], spec: Any = None) -> str:
    """Derive a display label from entity data.

    Priority order:
    1. spec.label_field (if defined in spec)
    2. spec.identifier_field (if defined in spec)
    3. Entity-specific label fields (hardcoded per entity type)
    4. Common label fields (title, name, etc.)
    5. First non-empty string field from spec

    Args:
        entity_type: Type of entity.
        data: Entity data dictionary.
        spec: Optional EntityDefSpec with field definitions for fallback.

    Returns:
        Derived label string.
    """
    # First priority: spec-defined label_field
    if spec and hasattr(spec, "label_field") and spec.label_field:
        if data.get(spec.label_field):
            return str(data[spec.label_field])

    # Second priority: spec-defined identifier_field (as fallback label)
    if spec and hasattr(spec, "identifier_field") and spec.identifier_field:
        if data.get(spec.identifier_field):
            return str(data[spec.identifier_field])

    # Check entity-specific label fields
    if entity_type in ENTITY_LABEL_FIELDS:
        for key in ENTITY_LABEL_FIELDS[entity_type]:
            if data.get(key):
                return str(data[key])

    # Fall back to generic label fields
    for key in LABEL_FIELDS:
        if data.get(key):
            return str(data[key])

    # Person special case: combine first and last name
    if data.get("first_name") or data.get("last_name"):
        parts = [data.get("first_name", ""), data.get("last_name", "")]
        label = " ".join(p for p in parts if p).strip()
        if label:
            return label

    # Spec-based fallback: first non-empty string field
    if spec and hasattr(spec, "fields"):
        from metaseed.specs.schema import FieldType

        for f in spec.fields:
            if f.type == FieldType.STRING and data.get(f.name):
                return str(data[f.name])[:50]

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


def normalize_reference_fields(data: dict[str, Any], helper: EntityHelper) -> dict[str, Any]:
    """Normalize reference fields in entity data to store IDs instead of embedded objects.

    When an MCP agent creates entities, it may pass embedded objects for reference
    fields (e.g., derives_from: [{name: "SOURCE-001", ...}]). This function
    normalizes such fields to store just the identifiers (e.g., ["SOURCE-001"]).

    Args:
        data: Entity data dictionary (will NOT be modified in-place).
        helper: EntityHelper for the entity type.

    Returns:
        New dictionary with normalized reference fields.
    """
    # Make a shallow copy to avoid modifying input
    result = copy.copy(data)

    # Get fields that reference other entities
    nested_fields = helper.nested_fields

    for field_name in nested_fields:
        if field_name not in result:
            continue

        value = result[field_name]
        if value is None:
            continue

        # Handle list fields
        if isinstance(value, list):
            normalized_list = []
            for item in value:
                if isinstance(item, dict):
                    # Extract identifier from embedded object
                    item_id = get_identifier(item)
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
            item_id = get_identifier(value)
            if item_id:
                result[field_name] = item_id

    return result
