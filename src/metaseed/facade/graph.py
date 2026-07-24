"""Tree and graph generation for entity visualization.

This module provides functions for generating hierarchical tree structures
and vis.js-compatible graph data from entity stores.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from metaseed.facade.node import EntityNode

if TYPE_CHECKING:
    from metaseed.facade.helper import EntityHelper
    from metaseed.facade.store import EntityStore

__all__ = ["get_tree", "to_graph"]


def get_tree(
    store: EntityStore,
    entities: dict[str, EntityHelper],
) -> list[dict[str, Any]]:
    """Get hierarchical tree for visualization.

    Returns tree structure starting from root nodes, with each node
    containing its children recursively.

    Args:
        store: EntityStore containing the entity instances.
        entities: Dictionary mapping entity type names to EntityHelpers.

    Returns:
        List of dicts representing the tree structure:
        [{"id": "...", "entity_type": "...", "label": "...", "children": [...]}]
    """
    roots = store.get_roots()

    def node_to_dict(node: EntityNode) -> dict[str, Any]:
        # Get label using helper's get_label for consistency
        helper = entities.get(node.entity_type)
        if helper and node.instance:
            label = helper.get_label(node.instance)
        else:
            label = node.label

        return {
            "id": node.id,
            "entity_type": node.entity_type,
            "label": label,
            "has_children": bool(node.children),
            "children": [node_to_dict(c) for c in node.children],
        }

    return [node_to_dict(r) for r in roots]


def to_graph(  # noqa: C901
    store: EntityStore,
    entities: dict[str, EntityHelper],
) -> dict[str, Any]:
    """Export entity graph in vis.js format.

    Builds nodes and edges for visualization. Includes:
    - Containment edges (parent-child, solid lines)
    - Reference edges (entity references, dashed lines)

    Args:
        store: EntityStore containing the entity instances.
        entities: Dictionary mapping entity type names to EntityHelpers.

    Returns:
        Dictionary with 'nodes' and 'edges' lists for vis.js.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Maps for resolving references by unique_id/alias
    unique_id_to_vis_id: dict[str, str] = {}

    def truncate(text: str, max_len: int = 25) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "..."

    def format_value(value: Any, max_len: int = 50) -> str:
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

    def build_tooltip(entity_type: str, label: str, data: dict[str, Any]) -> str:
        lines = [f"{entity_type}: {label}"]
        shown = 0
        for key, value in data.items():
            if shown >= 8:
                lines.append("...")
                break
            formatted = format_value(value)
            if (formatted and not isinstance(value, list)) or (
                isinstance(value, list) and value
            ):
                lines.append(f"{key}: {formatted}")
                shown += 1
        return "\n".join(lines)

    def process_node(node: EntityNode, parent_vis_id: str | None, level: int) -> None:
        vis_id = node.id

        # Get entity data
        entity_data = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            entity_data = node.instance.model_dump(exclude_none=True)

        # Map identifier to vis_id for reference resolution
        helper = entities.get(node.entity_type)
        if helper and helper.identifier_field:
            id_value = entity_data.get(helper.identifier_field)
            if id_value:
                unique_id_to_vis_id[str(id_value)] = vis_id

        # Get label
        if helper:
            label = helper.get_label(node.instance)
        else:
            label = node.label

        tooltip = build_tooltip(node.entity_type, label, entity_data)

        nodes.append(
            {
                "id": vis_id,
                "label": truncate(label, 25),
                "title": tooltip,
                "group": node.entity_type,
                "level": level,
            }
        )

        # Parent-child containment edge
        if parent_vis_id:
            edges.append(
                {
                    "id": f"{parent_vis_id}->{vis_id}",
                    "from": parent_vis_id,
                    "to": vis_id,
                }
            )

        # Process children
        for child in node.children:
            process_node(child, vis_id, level + 1)

    # First pass: build all nodes
    for root in store.get_roots():
        process_node(root, None, 0)

    # Second pass: add reference edges
    for node in store._instances.values():
        if not node.instance or not hasattr(node.instance, "model_dump"):
            continue

        vis_id = node.id
        entity_data = node.instance.model_dump(exclude_none=True)
        helper = entities.get(node.entity_type)
        if not helper:
            continue

        # Check reference fields (e.g., sample_ref -> Sample.alias)
        for field_name in helper.reference_fields:
            ref_value = entity_data.get(field_name)
            if not ref_value or not isinstance(ref_value, str):
                continue

            target_vis_id = unique_id_to_vis_id.get(ref_value)
            if target_vis_id and target_vis_id != vis_id:
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

        # Check nested fields for list references
        for field_name in helper.nested_fields:
            ref_value = entity_data.get(field_name)
            if not ref_value:
                continue

            ref_ids = []
            if isinstance(ref_value, list):
                for item in ref_value:
                    if isinstance(item, str):
                        ref_ids.append(item)
                    elif isinstance(item, dict):
                        from metaseed.repositories.helpers import get_identifier

                        item_id = get_identifier(item)
                        if item_id:
                            ref_ids.append(item_id)

            for ref_id in ref_ids:
                target_vis_id = unique_id_to_vis_id.get(ref_id)
                if target_vis_id and target_vis_id != vis_id:
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
