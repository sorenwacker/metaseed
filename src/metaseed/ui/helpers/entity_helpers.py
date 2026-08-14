"""Entity helper functions for UI routes.

Contains utility functions for walking nested entities, extracting
nested items, and collecting entities by type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade
    from metaseed.ui.state import AppState


def to_dict(item: Any, exclude_none: bool = True) -> dict[str, Any] | None:
    """Convert an item to a plain dictionary.

    Handles Pydantic models, dicts, and other types consistently.

    Args:
        item: Item to convert (Pydantic model, dict, or other).
        exclude_none: Whether to exclude None values from model_dump.

    Returns:
        Dictionary representation, or None if item cannot be converted.
    """
    if hasattr(item, "model_dump"):
        dumped: dict[str, Any] = item.model_dump(exclude_none=exclude_none)
        return dumped
    if isinstance(item, dict):
        return item.copy()
    return None


def walk_nested_entities(
    data: dict[str, Any],
    entity_type: str,
    facade: Any,
) -> list[tuple[str, dict[str, Any]]]:
    """Walk nested entities recursively, yielding (type, data) tuples.

    Traverses nested entity fields and collects all nested items
    with their types. Useful for collecting entities by type.

    Args:
        data: Root entity data dictionary.
        entity_type: Type of the root entity.
        facade: Profile facade for accessing entity helpers.

    Returns:
        List of (entity_type, data_dict) tuples for all nested entities.
    """
    results: list[tuple[str, dict[str, Any]]] = []

    def _walk(current_data: dict[str, Any], current_type: str) -> None:
        helper = getattr(facade, current_type, None)
        if not helper:
            return

        for field_name, nested_type in helper.nested_fields.items():
            nested_items = current_data.get(field_name)
            if not nested_items or not isinstance(nested_items, list):
                continue

            for item in nested_items:
                item_data = to_dict(item)
                if item_data:
                    results.append((nested_type, item_data))
                    _walk(item_data, nested_type)

    _walk(data, entity_type)
    return results


def extract_nested_items(instance: Any, helper: Any) -> dict[str, list[dict[str, Any]]]:
    """Extract nested items from an instance as dictionaries.

    Converts nested Pydantic models or dicts in an instance to a dictionary
    mapping field names to lists of plain dicts.

    Args:
        instance: Pydantic model instance with potential nested items.
        helper: EntityHelper with nested_fields information.

    Returns:
        Dictionary mapping nested field names to lists of item dicts.
    """
    result: dict[str, list[dict[str, Any]]] = {}

    if not hasattr(instance, "model_dump"):
        return result

    data = instance.model_dump(exclude_none=True)
    for field_name in helper.nested_fields:
        if data.get(field_name):
            items = data[field_name]
            if isinstance(items, list):
                result[field_name] = [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in items
                ]

    return result


def extract_nested_from_tree(
    node: Any, helper: Any, facade: Any = None
) -> dict[str, list[dict[str, Any]]]:
    """Extract nested items from tree children.

    When entities are created via MCP with parent_id, child entities are
    stored as separate tree nodes, not as nested objects in the parent.
    This function reconstructs the nested items from the tree structure.

    Children are matched by:
    1. Nested array fields (e.g., Study.samples -> Sample)
    2. Reference fields pointing to this entity (e.g., File.run_ref -> Run)

    Args:
        node: TreeNode with potential children.
        helper: EntityHelper with nested_fields mapping.
        facade: Optional ProfileFacade to find children via reference fields.

    Returns:
        Dictionary mapping field names to lists of child entity dicts.
    """
    result: dict[str, list[dict[str, Any]]] = {}

    if not node.children:
        return result

    # Build mapping: entity_type -> field_name from nested arrays
    type_to_field = {v: k for k, v in helper.nested_fields.items()}

    # Also find children via reference fields (e.g., File.run_ref -> Run)
    # These use a synthetic field name based on entity type (e.g., "files" for File)
    if facade:
        parent_type = node.entity_type

        for child in node.children:
            if child.entity_type in type_to_field:
                continue  # Already handled by nested array

            # Check if child has a reference field pointing to this parent —
            # through the public reference_fields property (the same one
            # validation.py uses), not by hand-parsing the private _spec.
            child_helper = getattr(facade, child.entity_type, None)
            if child_helper:
                for target_type, _target in child_helper.reference_fields.values():
                    if target_type == parent_type:
                        # Synthetic grouping key; internal to this dict, but
                        # naive pluralization ("Study" -> "studys") reads as
                        # a guessed field name, which this module family
                        # promises never to do.
                        key = f"_referenced_{child.entity_type.lower()}"
                        type_to_field[child.entity_type] = key
                        break

    for child in node.children:
        field_name = type_to_field.get(child.entity_type)
        if not field_name:
            continue

        if field_name not in result:
            result[field_name] = []

        if child.instance and hasattr(child.instance, "model_dump"):
            child_data = child.instance.model_dump(exclude_none=True)
            # Add node_id for reference when editing
            child_data["_node_id"] = child.id
            result[field_name].append(child_data)

    return result


def get_nested_items_for_edit(
    node: Any, helper: Any, facade: Any = None
) -> dict[str, list[dict[str, Any]]]:
    """Get all nested items for editing, combining instance data and tree children.

    This is the canonical function for getting nested items when editing an entity.
    It combines items from:
    1. The instance's nested fields (for inline nested objects)
    2. The tree's child nodes (for entities created via MCP with parent_id)
    3. Children linked via reference fields (e.g., File.run_ref -> Run)

    Args:
        node: TreeNode being edited.
        helper: EntityHelper with nested_fields mapping.
        facade: Optional ProfileFacade to find children via reference fields.

    Returns:
        Dictionary mapping field names to lists of entity dicts.
    """
    result: dict[str, list[dict[str, Any]]] = {}

    # First, get items from instance data
    if node.instance:
        instance_items = extract_nested_items(node.instance, helper)
        for field_name, items in instance_items.items():
            # Only include actual dicts, not string references
            result[field_name] = [item for item in items if isinstance(item, dict)]

    # Then, add items from tree children (includes reference-linked children if facade provided)
    tree_items = extract_nested_from_tree(node, helper, facade)
    for field_name, items in tree_items.items():
        if field_name not in result:
            result[field_name] = []
        # Add tree children that aren't already in result (by node_id)
        existing_ids = {item.get("_node_id") for item in result[field_name]}
        for item in items:
            if item.get("_node_id") not in existing_ids:
                result[field_name].append(item)

    return result


def collect_entities_by_type(  # noqa: C901
    state: AppState, facade: ProfileFacade
) -> dict[str, list[dict[str, Any]]]:
    """Collect all entities (root and nested) organized by type.

    Traverses nodes_by_id and nested items to extract all entities.

    Args:
        state: Application state containing nodes and nested items.
        facade: Profile facade for entity metadata.

    Returns:
        Dictionary mapping entity type to list of entity data:
        {
            "ObservationUnit": [
                {"value": "OU-1", "label": "Obs Unit 1", "data": {...}},
                ...
            ],
            ...
        }
    """
    entities_by_type: dict[str, list[dict[str, Any]]] = {}
    # Every entity is present twice over: as a stored node, and as the dict
    # still embedded in its parent's data. Offered both ways, the dropdown
    # listed each row twice. Two options with one value are indistinguishable
    # to whoever is choosing — picking either writes the same identifier — so
    # the second is dropped. (The export could not do this: two rows sharing an
    # identifier can still be two records. See f9efabc.)
    seen: set[tuple[str, str]] = set()

    def _extract_label(data: dict[str, Any]) -> tuple[str, str]:
        """Extract identifier and label from entity data."""
        identifier = ""
        label = ""

        for id_field in ["unique_id", "identifier", "name", "title"]:
            if data.get(id_field):
                identifier = str(data[id_field])
                break

        for label_field in ["title", "name", "description", "unique_id", "identifier"]:
            if data.get(label_field):
                label = str(data[label_field])
                break

        return identifier, label or identifier

    def add_entity(entity_type: str, data: dict[str, Any]) -> None:
        """Add an entity to the collection, once."""
        identifier, label = _extract_label(data)
        if identifier:
            if (entity_type, identifier) in seen:
                return
            seen.add((entity_type, identifier))

        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []
        entities_by_type[entity_type].append(
            {"value": identifier, "label": label, "data": data}
        )

    # Process root nodes and their nested entities
    for node in state.nodes_by_id.values():
        data = to_dict(node.instance) or {}
        add_entity(node.entity_type, data)

        # Add all nested entities using shared walker
        for nested_type, nested_data in walk_nested_entities(
            data, node.entity_type, facade
        ):
            add_entity(nested_type, nested_data)

    # Process current_nested_items (in-progress edits)
    if state.editing_node_id:
        editing_node = state.nodes_by_id.get(state.editing_node_id)
        if editing_node:
            helper = getattr(facade, editing_node.entity_type, None)
            if helper:
                for field_name, items in state.current_nested_items.items():
                    if field_name in helper.nested_fields:
                        nested_type = helper.nested_fields[field_name]
                        for item in items:
                            item_data = (
                                to_dict(item) if not isinstance(item, dict) else item
                            )
                            if item_data:
                                add_entity(nested_type, item_data)
                                for sub_type, sub_data in walk_nested_entities(
                                    item_data, nested_type, facade
                                ):
                                    add_entity(sub_type, sub_data)

    return entities_by_type


__all__ = [
    "collect_entities_by_type",
    "extract_nested_from_tree",
    "extract_nested_items",
    "get_nested_items_for_edit",
    "to_dict",
    "walk_nested_entities",
]
