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


def short_label(value: str) -> str:
    """The readable end of a label.

    An identifier is often the entity's IRI, and a trail of them wraps over two
    lines saying almost nothing: every crumb starts "https://example.org/". The
    last meaningful segment identifies it; the full value stays in the title.
    """
    text = str(value).strip().rstrip("/")
    if "://" not in text:
        return text
    tail = text.rsplit("/", 1)[-1]
    return tail or text


def crumb_label(entity_type: str, label: str | None) -> str:
    """How every crumb naming an entity reads: ``Type: what it is``.

    One rule for both builders. The edit form said "Catalog: <iri>" while the
    nested pages said "<iri>" alone, so the same trail read differently
    depending on which page drew it.
    """
    if not label:
        return entity_type
    return f"{entity_type}: {short_label(label)}"


def names_the_same_thing(field: str, entity_type: str) -> bool:
    """Whether a field crumb only repeats the type of the crumb after it.

    ``dataset > Dataset: …`` says it twice; ``contact_point > Kind: …`` does
    not, and there the field is the only thing that says which field it is.
    """
    return field.replace("_", "").lower() == entity_type.replace("_", "").lower()


def build_breadcrumb(state: AppState) -> list[dict[str, Any]]:
    """Build breadcrumb navigation from nested edit stack."""
    breadcrumb: list[dict[str, Any]] = []

    # Root entity (if editing)
    if state.editing_node_id:
        node = state.nodes_by_id.get(state.editing_node_id)
        if node:
            breadcrumb.append(
                {
                    "label": crumb_label(node.entity_type, node.label),
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
                # Through the same rule as every other crumb: this loop built
                # its own label, so a nested page said "STUDY-001" where the
                # edit form said "Study: STUDY-001" for the same entity.
                "label": crumb_label(ctx.entity_type, item_label)
                if item_label != f"{ctx.entity_type} {ctx.row_idx + 1}"
                else item_label,
                "entity_type": ctx.entity_type,
                "url": url,
            }
        )

    return breadcrumb


def build_ancestor_breadcrumb(state: AppState, node: Any) -> list[dict[str, Any]]:
    """Build a breadcrumb from a node's own containment chain.

    :func:`build_breadcrumb` reads the nested edit stack, which is empty when an
    entity is opened directly — from the graph, a link, or a table row. The
    chain recorded on the node itself (``parent_id`` and ``parent_field``,
    ADR 006) is what makes the parent reachable there.

    Args:
        state: UI state holding the nodes by id.
        node: The node being edited.

    Returns:
        Entries root-first: each ancestor as a link, the field it holds the next
        entry in as a plain label, and the edited node itself without a link. A
        field is a label rather than a link because a single-``entity`` field
        has no table view to open.
    """
    chain: list[Any] = []
    seen: set[str] = set()
    current: Any = node
    while current is not None:
        if current.id in seen:  # a cycle would otherwise loop forever
            break
        seen.add(current.id)
        chain.append(current)
        parent_id = getattr(current, "parent_id", None)
        current = state.nodes_by_id.get(parent_id) if parent_id else None

    breadcrumb: list[dict[str, Any]] = []
    for depth, ancestor in enumerate(reversed(chain)):
        label = crumb_label(ancestor.entity_type, ancestor.label)
        is_edited = ancestor.id == node.id
        breadcrumb.append(
            {
                "label": label,
                "entity_type": ancestor.entity_type,
                "url": None
                if is_edited
                else f"/form/{ancestor.entity_type}/{ancestor.id}",
            }
        )
        # The field lives on the child, naming where the parent holds it.
        child = chain[len(chain) - depth - 2] if depth + 2 <= len(chain) else None
        # A field crumb that only repeats the type of the crumb after it says
        # the same thing twice: "dataset > Dataset: ...".
        if child is not None and names_the_same_thing(
            getattr(child, "parent_field", "") or "", child.entity_type
        ):
            continue
        field = getattr(child, "parent_field", None) if child else None
        if field:
            breadcrumb.append({"label": field, "entity_type": None, "url": None})

    return breadcrumb


__all__ = [
    "build_ancestor_breadcrumb",
    "build_breadcrumb",
    "error_response",
    "get_parent_id_fields",
    "get_reference_fields",
]
