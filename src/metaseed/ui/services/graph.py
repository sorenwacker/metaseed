"""Graph visualization service.

Builds graph data (nodes and edges) from the AppState entity tree
for visualization with vis.js.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


def truncate(text: str, max_len: int = 25) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


def _format_value(value: Any, max_len: int = 50) -> str:
    """Format a value for tooltip display."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, date | datetime):
        return str(value)
    if isinstance(value, list):
        if not value:
            return ""
        if len(value) <= 3:
            return ", ".join(str(v) for v in value)
        return f"{len(value)} items"
    if isinstance(value, dict):
        return "[object]"
    text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _build_tooltip(entity_type: str, label: str, data: dict) -> str:
    """Build tooltip showing entity data.

    Args:
        entity_type: Type of entity.
        label: Entity label.
        data: Entity data dictionary.

    Returns:
        Plain text string for vis.js tooltip (uses newlines for line breaks).
    """
    # Start with header
    lines = [f"{entity_type}: {label}"]

    # Add key fields (skip empty values and nested lists)
    shown = 0
    for key, value in data.items():
        if shown >= 8:  # Limit tooltip size
            lines.append("...")
            break
        formatted = _format_value(value)
        if formatted and not isinstance(value, list) or (isinstance(value, list) and value):
            lines.append(f"{key}: {formatted}")
            shown += 1

    return "\n".join(lines)


def build_graph(state: AppState) -> dict:
    """Build graph data from entity tree.

    Uses state.get_tree_data() as the single source of truth for hierarchy,
    then converts to vis.js format. Also resolves entity reference fields
    (like material_source) to show reference edges.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Dictionary with 'nodes' and 'edges' lists for vis.js.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # Maps for resolving references by unique_id
    unique_id_to_vis_id: dict[str, str] = {}
    tree_id_to_vis_id: dict[str, str] = {}

    def process_tree_node(
        tree_item: dict, parent_vis_id: str | None = None, level: int = 0
    ) -> None:
        """Process a tree node and its children recursively."""
        # Use tree ID as vis ID for stable identification across requests
        vis_id = tree_item["id"]
        tree_id_to_vis_id[tree_item["id"]] = vis_id

        # Get entity data for tooltip and unique_id mapping
        entity_data = {}
        tree_node = state.nodes_by_id.get(tree_item["id"])
        if tree_node and tree_node.instance and hasattr(tree_node.instance, "model_dump"):
            entity_data = tree_node.instance.model_dump(exclude_none=True)
            # Map unique_id to vis_id for reference resolution
            if entity_data.get("unique_id"):
                unique_id_to_vis_id[entity_data["unique_id"]] = vis_id

        tooltip = _build_tooltip(
            tree_item["entity_type"],
            tree_item["label"],
            entity_data,
        )

        nodes.append(
            {
                "id": vis_id,
                "label": truncate(tree_item["label"], 25),
                "title": tooltip,
                "group": tree_item["entity_type"],
                "level": level,
            }
        )

        # Parent-child containment edge (solid)
        if parent_vis_id:
            edges.append(
                {
                    "id": f"{parent_vis_id}->{vis_id}",
                    "from": parent_vis_id,
                    "to": vis_id,
                }
            )

        # Process children recursively
        for child in tree_item.get("children", []):
            process_tree_node(child, vis_id, level + 1)

    # First pass: build all nodes
    tree_data = state.get_tree_data()
    for root_item in tree_data:
        process_tree_node(root_item)

    # Second pass: add entity reference edges
    # Look for fields that reference other entities by unique_id
    facade = state.get_or_create_facade()

    for tree_id, tree_node in state.nodes_by_id.items():
        if not tree_node.instance or not hasattr(tree_node.instance, "model_dump"):
            continue

        vis_id = tree_id_to_vis_id.get(tree_id)
        if not vis_id:
            continue

        entity_data = tree_node.instance.model_dump(exclude_none=True)
        helper = getattr(facade, tree_node.entity_type, None)
        if not helper:
            continue

        # Check for entity reference fields
        for field_name in getattr(helper, "nested_fields", {}):
            ref_value = entity_data.get(field_name)
            if not ref_value or isinstance(ref_value, list | dict):
                continue

            # ref_value should be the unique_id of the referenced entity
            target_vis_id = unique_id_to_vis_id.get(str(ref_value))
            if target_vis_id and target_vis_id != vis_id:
                # Add reference edge (dashed, different color)
                edges.append(
                    {
                        "id": f"{vis_id}->{target_vis_id}:{field_name}",
                        "from": vis_id,
                        "to": target_vis_id,
                        "dashes": True,
                        "label": field_name,
                        "font": {"size": 8},
                    }
                )

    return {"nodes": nodes, "edges": edges}
