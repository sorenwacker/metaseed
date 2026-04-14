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
    """Get all reference fields for an entity type by parsing YAML validation rules.

    Reference rules are defined in the spec like:
        - name: sample_observation_unit_reference
          applies_to: [Sample]
          field: observation_unit_id
          reference: ObservationUnit.unique_id

    Args:
        profile: Profile name (e.g., "miappe").
        version: Profile version (e.g., "1.1").
        entity_type: Entity type name (e.g., "Sample").

    Returns:
        Dictionary mapping field names to their reference info:
        {
            "observation_unit_id": {
                "target_entity": "ObservationUnit",
                "target_field": "unique_id"
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
            if id_field in data and data[id_field]:
                identifier = str(data[id_field])
                break

        # Try to build a label from multiple fields
        for label_field in ["title", "name", "description", "unique_id", "identifier"]:
            if label_field in data and data[label_field]:
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
            if field_name in data and data[field_name]:
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
                    if key in item and item[key]:
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
