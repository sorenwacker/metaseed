"""Graph visualization service.

Builds graph data (nodes and edges) from the AppState entity tree
for visualization with vis.js.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.ui.state import AppState, TreeNode


def truncate(text: str, max_len: int = 25) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


def build_graph(state: AppState) -> dict:
    """Build graph data from entity tree.

    Traverses the entity tree (including nested entities) and creates
    nodes and edges suitable for vis.js network visualization.
    Deduplicates nodes based on entity type and identifier/name.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Dictionary with 'nodes' and 'edges' lists for vis.js.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    node_counter = 0
    # Track existing nodes by (entity_type, identifier) to deduplicate
    node_lookup: dict[tuple[str, str], str] = {}

    def get_node_id() -> str:
        """Generate unique node ID."""
        nonlocal node_counter
        node_counter += 1
        return f"n{node_counter}"

    def get_entity_key(data: dict, _entity_type: str) -> str:
        """Get unique key for an entity for deduplication."""
        # Try common identifier fields
        for field in ["unique_id", "identifier", "name", "filename", "title"]:
            if data.get(field):
                return str(data[field])
        # Fall back to a hash of the data for truly anonymous entities
        return str(hash(frozenset(str(v) for v in data.values() if v)))

    def add_or_get_node(entity_type: str, label: str, data: dict) -> str:
        """Add a node or return existing node ID if duplicate."""
        # Determine display group based on type field
        display_group = entity_type
        if entity_type == "OtherMaterial" and data.get("type"):
            type_value = data["type"]
            if "Extract" in type_value:
                display_group = "LabeledExtract" if "Labeled" in type_value else "Extract"
        elif entity_type == "MaterialRef" and data.get("type"):
            # MaterialRef uses type to indicate actual material type
            display_group = data["type"]

        key = (display_group, get_entity_key(data, entity_type))

        if key in node_lookup:
            return node_lookup[key]

        vis_id = get_node_id()
        node_lookup[key] = vis_id

        nodes.append(
            {
                "id": vis_id,
                "label": truncate(label, 25),
                "title": f"{display_group}: {label}",
                "group": display_group,
            }
        )
        return vis_id

    def add_tree_node(node: TreeNode, parent_vis_id: str | None = None) -> None:
        """Add a TreeNode and its children to the graph."""
        data = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)

        vis_id = add_or_get_node(node.entity_type, node.label, data)

        if parent_vis_id:
            edge = {"from": parent_vis_id, "to": vis_id}
            if edge not in edges:
                edges.append(edge)

        # Process nested entities from instance data
        if data:
            add_nested_entities(data, node.entity_type, vis_id, state)

    def add_nested_entities(
        data: dict, entity_type: str, parent_vis_id: str, state: AppState
    ) -> None:
        """Add nested entities from instance data."""
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return

        for field_name, nested_type in helper.nested_fields.items():
            nested_items = data.get(field_name, [])
            if not nested_items or not isinstance(nested_items, list):
                continue

            for item in nested_items:
                if hasattr(item, "model_dump"):
                    item_data = item.model_dump(exclude_none=True)
                elif isinstance(item, dict):
                    item_data = item
                else:
                    continue

                # Get label for nested item
                label = get_entity_label(item_data, nested_type, facade)
                vis_id = add_or_get_node(nested_type, label, item_data)

                edge = {"from": parent_vis_id, "to": vis_id}
                if edge not in edges:
                    edges.append(edge)

                # Recursively process nested children
                add_nested_entities(item_data, nested_type, vis_id, state)

    def get_entity_label(data: dict, entity_type: str, _facade: object) -> str:
        """Get display label for an entity."""
        # Special handling for ISA Characteristic (category: value format)
        if entity_type == "Characteristic":
            category = data.get("category", "")
            value = data.get("value", "")
            if isinstance(category, dict):
                category = category.get("term", category.get("name", ""))
            if category and value:
                return f"{category}: {value}"
            elif category:
                return str(category)
            elif value:
                return str(value)

        # Special handling for Person (ISA uses last_name/first_name)
        if entity_type == "Person":
            last = data.get("last_name", data.get("family_name", ""))
            first = data.get("first_name", data.get("given_name", ""))
            if last and first:
                return f"{first} {last}"
            elif last:
                return last
            elif first:
                return first

        # Try common label fields
        for field in [
            "title",
            "name",
            "unique_id",
            "identifier",
            "filename",
            "parameter",
            "event_type",
            "protocol_type",
            "category",
        ]:
            if data.get(field):
                return str(data[field])

        return f"New {entity_type}"

    # Process all root nodes in the entity tree
    for root_node in state.entity_tree:
        add_tree_node(root_node)

    return {"nodes": nodes, "edges": edges}
