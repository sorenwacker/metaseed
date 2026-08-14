"""Navigation helper functions for UI routes.

Contains utility functions for breadcrumb building, error responses,
and reference field handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


def error_response(
    request: Request, templates: Jinja2Templates, message: str
) -> HTMLResponse:
    """Create an error response with notification."""
    return templates.TemplateResponse(
        request,
        "components/notification.html",
        {
            "type": "error",
            "message": message,
        },
    )


def get_reference_fields(
    profile: str, version: str, entity_type: str
) -> dict[str, dict[str, str]]:
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
    except SpecLoadError:
        return {}

    reference_fields: dict[str, dict[str, str]] = {}

    # Check field definitions for parent_ref or reference attribute
    entity_spec = spec.entities.get(entity_type)
    if entity_spec:
        for field in entity_spec.fields:
            # Check parent_ref first (explicit parent reference)
            ref_value = None
            if hasattr(field, "parent_ref") and field.parent_ref:
                ref_value = field.parent_ref
            # Fall back to reference attribute (entity reference)
            elif hasattr(field, "reference") and field.reference:
                ref_value = field.reference

            if ref_value:
                parts = ref_value.split(".")
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
            parts = rule.reference.split(".")
            if len(parts) != 2:
                # rule.reference is free-form text from the spec builder; a value
                # without exactly one dot is not an entity reference. Skip rather
                # than raise ValueError on the unpacking.
                continue
            target_entity, target_field = parts
            reference_fields[rule.field] = {
                "target_entity": target_entity,
                "target_field": target_field,
            }

    return reference_fields


def get_parent_id_fields(
    reference_fields: dict[str, dict[str, str]], parent_entity_type: str
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


def build_breadcrumb(state: AppState) -> list[dict[str, Any]]:
    """Build breadcrumb navigation from nested edit stack."""
    breadcrumb: list[dict[str, Any]] = []

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
                # Use the first field from spec as label (convention)
                facade = state.get_or_create_facade()
                helper = getattr(facade, ctx.entity_type, None)
                if helper and helper.identifier_field:
                    value = item.get(helper.identifier_field)
                    if value:
                        item_label = str(value)

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


__all__ = [
    "build_breadcrumb",
    "error_response",
    "get_parent_id_fields",
    "get_reference_fields",
]
