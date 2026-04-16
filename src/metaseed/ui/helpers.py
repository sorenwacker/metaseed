"""Helper functions for UI routes.

Contains utility functions for form handling, table rendering,
validation formatting, and breadcrumb navigation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.requests import Request

from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade

    from .state import AppState


def get_field_data(helper: Any) -> list[dict]:
    """Get field data for template rendering."""
    fields = []
    for field_name in helper.all_fields:
        info = helper.field_info(field_name)
        fields.append(
            {
                "name": field_name,
                "type": info["type"],
                "required": info["required"],
                "description": info.get("description", ""),
                "items": info.get("items"),
            }
        )
    return fields


def is_nested_field(field: dict) -> bool:
    """Check if a field represents a nested entity (list of entities or single entity)."""
    if field["type"] == "entity":
        return True
    if field["type"] == "list":
        items = field.get("items")
        if items and items not in ("string", "int", "float", "bool"):
            return True
    return False


def collect_form_values(form_data: dict, helper: Any) -> dict:
    """Collect form values into a dictionary."""
    values = {}
    for field_name in helper.all_fields:
        value = form_data.get(field_name)
        if value is None or value == "":
            continue

        info = helper.field_info(field_name)
        field_type = info["type"]

        if field_type == "integer":
            try:
                value = int(value)
            except ValueError:
                continue
        elif field_type == "float":
            try:
                value = float(value)
            except ValueError:
                continue
        elif field_type == "boolean":
            value = value.lower() in ("true", "1", "yes", "on")
        elif field_type == "list" and info.get("items") == "string":
            value = [line.strip() for line in str(value).split("\n") if line.strip()]

        values[field_name] = value

    return values


def format_validation_errors(e: ValidationError) -> str:
    """Format validation errors for display with user-friendly messages."""
    friendly_messages = []
    for err in e.errors():
        field = ".".join(str(loc) for loc in err["loc"])
        msg = err["msg"]

        # Make common error messages more user-friendly
        if "pattern" in msg.lower() and "email" in field.lower():
            msg = "Invalid email format"
        elif "pattern" in msg.lower() and ("date" in field.lower() or "date" in msg.lower()):
            msg = "Invalid date format (use YYYY-MM-DD)"
        elif "pattern" in msg.lower() and "orcid" in field.lower():
            msg = "Invalid ORCID format (use XXXX-XXXX-XXXX-XXXX)"
        elif "pattern" in msg.lower():
            msg = "Invalid format"
        elif "required" in msg.lower():
            msg = "This field is required"

        friendly_messages.append(f"{field}: {msg}")

    return "; ".join(friendly_messages)


def error_response(request: Request, templates: Jinja2Templates, message: str) -> HTMLResponse:
    """Create an error response with notification."""
    return templates.TemplateResponse(
        request,
        "components/notification.html",
        {
            "type": "error",
            "message": message,
        },
    )


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
    helper = getattr(facade, entity_type, None)
    if not helper:
        return {}

    # Use provided items_source or fall back to state.current_nested_items
    source = items_source if items_source is not None else state.current_nested_items

    inline_tables = {}
    for field_name, nested_type in helper.nested_fields.items():
        col_info = get_table_column_info(facade, nested_type)

        # Get items from source
        items = source.get(field_name, [])

        # Format rows
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


def get_items_store(state: AppState, parent_entity_type: str, field_name: str) -> tuple[dict, list]:
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


def get_reference_fields(profile: str, version: str, entity_type: str) -> dict[str, dict]:
    """Get all reference fields for an entity type.

    Checks two sources:
    1. Field definitions with parent_ref attribute (e.g., parent_ref: Study.identifier)
    2. Validation rules with reference attribute (legacy)

    Args:
        profile: Profile name (e.g., "miappe").
        version: Profile version (e.g., "1.1").
        entity_type: Entity type name (e.g., "Sample").

    Returns:
        Dictionary mapping field names to their reference info:
        {
            "study_id": {
                "target_entity": "Study",
                "target_field": "identifier"
            },
            ...
        }
    """
    loader = SpecLoader(profile=profile)
    try:
        spec = loader.load_profile(version=version, profile=profile)
    except Exception:
        return {}

    reference_fields = {}

    # Check field definitions for parent_ref attribute
    entity_spec = spec.entities.get(entity_type)
    if entity_spec:
        for field in entity_spec.fields:
            if hasattr(field, "parent_ref") and field.parent_ref:
                parts = field.parent_ref.split(".")
                if len(parts) == 2:
                    reference_fields[field.name] = {
                        "target_entity": parts[0],
                        "target_field": parts[1],
                    }

    # Also check validation rules (for backwards compatibility)
    for rule in spec.validation_rules:
        if not rule.reference or not rule.field:
            continue

        applies_to = rule.applies_to
        if isinstance(applies_to, str):
            applies_to = [applies_to] if applies_to != "all" else []

        if entity_type in applies_to:
            target_entity, target_field = rule.reference.split(".")
            reference_fields[rule.field] = {
                "target_entity": target_entity,
                "target_field": target_field,
            }

    return reference_fields


def get_parent_id_fields(
    reference_fields: dict[str, dict], parent_entity_type: str
) -> dict[str, str]:
    """Get fields that reference the parent entity and should be auto-filled.

    Args:
        reference_fields: Reference field definitions from get_reference_fields().
        parent_entity_type: The parent entity type (e.g., "Study").

    Returns:
        Dictionary mapping field names to the target field name:
        {
            "study_id": "unique_id",  # study_id references Study.unique_id
        }
    """
    parent_id_fields = {}
    for field_name, ref_info in reference_fields.items():
        if ref_info["target_entity"] == parent_entity_type:
            parent_id_fields[field_name] = ref_info["target_field"]
    return parent_id_fields


def get_parent_identifier(state: AppState, parent_entity_type: str, target_field: str) -> str:
    """Get the parent entity's identifier value.

    Args:
        state: Application state.
        parent_entity_type: The parent entity type.
        target_field: The field to get (e.g., "unique_id", "identifier").

    Returns:
        The parent's identifier value, or empty string if not found.
    """
    # Check if we're editing a root node
    if state.editing_node_id:
        node = state.nodes_by_id.get(state.editing_node_id)
        if node and node.entity_type == parent_entity_type and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)
            return str(data.get(target_field, ""))

    # Check nested edit stack for parent context
    for ctx in reversed(state.nested_edit_stack):
        if ctx.entity_type == parent_entity_type:
            # The parent is in the nested stack, get its data
            # This would be the item at ctx.row_idx in the parent's nested items
            pass

    return ""


def collect_entities_by_type(state: AppState, facade: ProfileFacade) -> dict[str, list[dict]]:
    """Collect all entities (root and nested) organized by type.

    Traverses nodes_by_id and nested items to extract all entities.

    Args:
        state: Application state containing nodes and nested items.
        facade: Profile facade for entity metadata.

    Returns:
        Dictionary mapping entity type to list of entity data:
        {
            "ObservationUnit": [
                {"identifier": "OU-1", "label": "Obs Unit 1", "data": {...}},
                ...
            ],
            ...
        }
    """
    entities_by_type: dict[str, list[dict]] = {}

    def add_entity(entity_type: str, data: dict) -> None:
        """Add an entity to the collection."""
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []

        # Extract identifier and label for display
        identifier = ""
        label = ""

        # Try common ID field names
        for id_field in ["unique_id", "identifier", "name", "title"]:
            if data.get(id_field):
                identifier = str(data[id_field])
                break

        # Try to build a label from multiple fields
        for label_field in ["title", "name", "description", "unique_id", "identifier"]:
            if data.get(label_field):
                label = str(data[label_field])
                break

        if not label:
            label = identifier

        entities_by_type[entity_type].append(
            {
                "value": identifier,
                "label": label,
                "data": data,
            }
        )

    def extract_nested(data: dict, entity_type: str) -> None:
        """Recursively extract nested entities."""
        helper = getattr(facade, entity_type, None)
        if not helper:
            return

        for field_name, nested_type in helper.nested_fields.items():
            if data.get(field_name):
                nested_items = data[field_name]
                if isinstance(nested_items, list):
                    for item in nested_items:
                        if hasattr(item, "model_dump"):
                            item_data = item.model_dump(exclude_none=True)
                        elif isinstance(item, dict):
                            item_data = item.copy()
                        else:
                            continue
                        add_entity(nested_type, item_data)
                        extract_nested(item_data, nested_type)

    # Process root nodes
    for node in state.nodes_by_id.values():
        if hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)
        else:
            data = {}
        add_entity(node.entity_type, data)
        extract_nested(data, node.entity_type)

    # Process current_nested_items (in-progress edits)
    for field_name, items in state.current_nested_items.items():
        # Try to determine the entity type from context
        if state.editing_node_id:
            editing_node = state.nodes_by_id.get(state.editing_node_id)
            if editing_node:
                helper = getattr(facade, editing_node.entity_type, None)
                if helper and field_name in helper.nested_fields:
                    nested_type = helper.nested_fields[field_name]
                    for item in items:
                        if isinstance(item, dict):
                            add_entity(nested_type, item)
                            extract_nested(item, nested_type)

    return entities_by_type


def build_breadcrumb(state: AppState) -> list[dict]:
    """Build breadcrumb navigation from nested edit stack."""
    breadcrumb = []

    # Root entity (if editing)
    if state.editing_node_id:
        node = state.nodes_by_id.get(state.editing_node_id)
        if node:
            breadcrumb.append(
                {
                    "label": node.label or node.entity_type,
                    "entity_type": node.entity_type,
                    "url": f"/form/{node.entity_type}/{node.id}",
                }
            )

    # Show all nested contexts with navigation
    for i, ctx in enumerate(state.nested_edit_stack):
        is_last = i == len(state.nested_edit_stack) - 1

        # Get label from the nested item data
        item_label = f"{ctx.entity_type} {ctx.row_idx + 1}"
        if i == 0:
            # First level - items are in current_nested_items
            items = state.current_nested_items.get(ctx.field_name, [])
        else:
            # Deeper levels - items are in parent context's nested_items
            parent_ctx = state.nested_edit_stack[i - 1]
            items = parent_ctx.nested_items.get(ctx.field_name, [])

        if ctx.row_idx < len(items):
            item = items[ctx.row_idx]
            if isinstance(item, dict):
                for key in ["title", "name", "unique_id", "identifier"]:
                    if item.get(key):
                        item_label = str(item[key])
                        break

        # Build URL for navigating to this nested item
        if is_last:
            # Current item - no link
            url = None
        else:
            # Previous items - link to edit them
            url = f"/nested/{ctx.parent_entity_type}/{ctx.field_name}/{ctx.row_idx}"

        breadcrumb.append(
            {
                "label": item_label,
                "entity_type": ctx.entity_type,
                "url": url,
            }
        )

    return breadcrumb
