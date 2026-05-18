"""Graph visualization service.

Builds graph data (nodes and edges) from the AppState entity tree
for visualization with vis.js.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


def truncate(text: str, max_len: int = 25) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


def build_graph(state: AppState) -> dict:
    """Build graph data from entity tree.

    Uses state.get_tree_data() as the single source of truth for hierarchy,
    then converts to vis.js format.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Dictionary with 'nodes' and 'edges' lists for vis.js.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    node_counter = 0

    def get_node_id() -> str:
        """Generate unique node ID."""
        nonlocal node_counter
        node_counter += 1
        return f"n{node_counter}"

    def process_tree_node(
        tree_item: dict, parent_vis_id: str | None = None, level: int = 0
    ) -> None:
        """Process a tree node and its children recursively."""
        vis_id = get_node_id()

        nodes.append(
            {
                "id": vis_id,
                "label": truncate(tree_item["label"], 25),
                "title": f"{tree_item['entity_type']}: {tree_item['label']}",
                "group": tree_item["entity_type"],
                "level": level,
            }
        )

        if parent_vis_id:
            edges.append({"from": parent_vis_id, "to": vis_id})

        # Process children recursively
        for child in tree_item.get("children", []):
            process_tree_node(child, vis_id, level + 1)

    # Use get_tree_data() as single source of truth
    tree_data = state.get_tree_data()
    for root_item in tree_data:
        process_tree_node(root_item)

    return {"nodes": nodes, "edges": edges}
