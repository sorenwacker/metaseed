"""Table helper functions for UI routes.

Contains utility functions for building and formatting inline tables,
table columns, and managing items stores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade

    from .state import AppState


def infer_entity_type_from_field(
    facade: ProfileFacade,
    parent_entity_type: str,
    field_name: str,
) -> str | None:
    """Infer the nested entity type from a field name.

    First checks the parent's nested_fields spec. If not found,
    infers from field name convention (e.g., "files" -> "File").

    Args:
        facade: Profile facade for entity lookups.
        parent_entity_type: Parent entity type (e.g., "Run").
        field_name: Field name (e.g., "files", "run_attributes").

    Returns:
        Entity type string if found, None otherwise.
    """
    parent_helper = getattr(facade, parent_entity_type, None)
    if not parent_helper:
        return None

    # Check spec-defined nested fields first
    entity_type = parent_helper.nested_fields.get(field_name)
    if entity_type:
        return entity_type

    # Infer from field name convention: "files" -> "File"
    inferred_type = field_name.rstrip("s").capitalize()
    if inferred_type in facade.entities:
        return inferred_type

    return None


def get_table_columns(facade: ProfileFacade, entity_type: str) -> list[str]:
    """Get table columns for a nested entity type."""
    helper = getattr(facade, entity_type, None)
    if not helper:
        return ["value"]

    cols = list(helper.required_fields) + list(helper.optional_fields)
    nested = set(helper.nested_fields.keys())
    return [c for c in cols if c not in nested]


def get_table_column_info(facade: ProfileFacade, entity_type: str) -> dict:
    """Get complete column info for a table (types, constraints, required).

    Returns dict with keys: columns, column_types, column_constraints, required_columns
    """
    helper = getattr(facade, entity_type, None)
    if not helper:
        return {
            "columns": ["value"],
            "column_types": {"value": "string"},
            "column_constraints": {},
            "required_columns": set(),
            "has_nested_children": False,
        }

    cols = list(helper.required_fields) + list(helper.optional_fields)
    nested = set(helper.nested_fields.keys())
    columns = [c for c in cols if c not in nested]

    column_types = {}
    column_constraints = {}
    for col in columns:
        info = helper.field_info(col)
        column_types[col] = info.get("type", "string")
        constraints = info.get("constraints", {})
        if constraints:
            column_constraints[col] = constraints

    return {
        "columns": columns,
        "column_types": column_types,
        "column_constraints": column_constraints,
        "required_columns": set(helper.required_fields),
        "has_nested_children": bool(helper.nested_fields),
    }


def build_inline_tables(
    state: AppState,
    facade: ProfileFacade,
    entity_type: str,
    items_source: dict[str, list] | None = None,
) -> dict[str, dict]:
    """Build inline table data for all nested fields of an entity type.

    Args:
        state: Application state containing nested items.
        facade: Profile facade for entity metadata.
        entity_type: Parent entity type (e.g., "Study").
        items_source: Optional dict to get items from instead of state.current_nested_items.
                     Used when building tables for nested edit contexts.

    Returns:
        Dictionary mapping field names to table data:
        {
            "contacts": {
                "columns": [...],
                "rows": [...],
                "column_types": {...},
                ...
            },
            ...
        }
    """
    # Import here to avoid circular imports
    from .navigation_helpers import get_parent_id_fields, get_reference_fields

    helper = getattr(facade, entity_type, None)
    if not helper:
        return {}

    # Use provided items_source or fall back to state.current_nested_items
    source = items_source if items_source is not None else state.current_nested_items

    inline_tables = {}

    # Build map of field_name -> nested_type from spec
    field_to_type = dict(helper.nested_fields)

    # Also include reference-linked children from source (e.g., files linked via run_ref)
    for field_name in source:
        if field_name not in field_to_type:
            inferred_type = infer_entity_type_from_field(
                facade, entity_type, field_name
            )
            if inferred_type:
                field_to_type[field_name] = inferred_type

    for field_name, nested_type in field_to_type.items():
        col_info = get_table_column_info(facade, nested_type)

        # Get items from source
        items = source.get(field_name, [])

        # Format rows
        rows = format_table_rows(items)

        # Get reference fields
        ref_fields = get_reference_fields(
            profile=state.profile,
            version=facade.version,
            entity_type=nested_type,
        )

        # Get parent ID fields (fields that reference parent entity)
        parent_id_fields = get_parent_id_fields(ref_fields, entity_type)

        # Filter out parent ID fields from display columns (relationship is implied by nesting)
        display_columns = [c for c in col_info["columns"] if c not in parent_id_fields]

        inline_tables[field_name] = {
            "columns": display_columns,
            "rows": rows,
            "column_types": col_info["column_types"],
            "column_constraints": col_info["column_constraints"],
            "required_columns": col_info["required_columns"],
            "has_nested_children": col_info["has_nested_children"],
            "reference_fields": ref_fields,
            "parent_id_fields": parent_id_fields,
            "nested_entity_type": nested_type,
        }

    return inline_tables


def get_items_store(
    state: AppState, parent_entity_type: str, field_name: str
) -> tuple[dict, list]:
    """Get the correct items store and items list based on context.

    Returns (items_store dict, items list for field_name).
    """
    nested_context = state.nested_edit_stack[-1] if state.nested_edit_stack else None
    if nested_context and nested_context.entity_type == parent_entity_type:
        items_store = nested_context.nested_items
    else:
        items_store = state.current_nested_items

    if field_name not in items_store:
        items_store[field_name] = []

    return items_store, items_store[field_name]


def format_table_rows(items: list) -> list[dict]:
    """Format items for table row rendering."""
    rows = []
    for i, item in enumerate(items):
        if hasattr(item, "model_dump"):
            row = item.model_dump(exclude_none=True)
        elif isinstance(item, dict):
            row = item.copy()
        else:
            row = {"value": str(item)}
        row["_idx"] = i
        rows.append(row)
    return rows


__all__ = [
    "build_inline_tables",
    "format_table_rows",
    "get_items_store",
    "get_table_column_info",
    "get_table_columns",
]
