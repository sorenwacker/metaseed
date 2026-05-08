"""Entity helper functions for UI routes.

Contains utility functions for walking nested entities, extracting
nested items, and collecting entities by type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade

    from .state import AppState


def to_dict(item: Any, exclude_none: bool = True) -> dict | None:
    """Convert an item to a plain dictionary.

    Handles Pydantic models, dicts, and other types consistently.

    Args:
        item: Item to convert (Pydantic model, dict, or other).
        exclude_none: Whether to exclude None values from model_dump.

    Returns:
        Dictionary representation, or None if item cannot be converted.
    """
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=exclude_none)
    if isinstance(item, dict):
        return item.copy()
    return None


def walk_nested_entities(
    data: dict,
    entity_type: str,
    facade: Any,
) -> list[tuple[str, dict]]:
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
    results: list[tuple[str, dict]] = []

    def _walk(current_data: dict, current_type: str) -> None:
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


def extract_nested_items(instance: Any, helper: Any) -> dict[str, list[dict]]:
    """Extract nested items from an instance as dictionaries.

    Converts nested Pydantic models or dicts in an instance to a dictionary
    mapping field names to lists of plain dicts.

    Args:
        instance: Pydantic model instance with potential nested items.
        helper: EntityHelper with nested_fields information.

    Returns:
        Dictionary mapping nested field names to lists of item dicts.
    """
    result: dict[str, list[dict]] = {}

    if not hasattr(instance, "model_dump"):
        return result

    data = instance.model_dump(exclude_none=True)
    for field_name in helper.nested_fields:
        if data.get(field_name):
            items = data[field_name]
            if isinstance(items, list):
                result[field_name] = [
                    item.model_dump() if hasattr(item, "model_dump") else item for item in items
                ]

    return result


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

    def _extract_label(data: dict) -> tuple[str, str]:
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

    def add_entity(entity_type: str, data: dict) -> None:
        """Add an entity to the collection."""
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []

        identifier, label = _extract_label(data)
        entities_by_type[entity_type].append({"value": identifier, "label": label, "data": data})

    # Process root nodes and their nested entities
    for node in state.nodes_by_id.values():
        data = to_dict(node.instance) or {}
        add_entity(node.entity_type, data)

        # Add all nested entities using shared walker
        for nested_type, nested_data in walk_nested_entities(data, node.entity_type, facade):
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
                            item_data = to_dict(item) if not isinstance(item, dict) else item
                            if item_data:
                                add_entity(nested_type, item_data)
                                for sub_type, sub_data in walk_nested_entities(
                                    item_data, nested_type, facade
                                ):
                                    add_entity(sub_type, sub_data)

    return entities_by_type


__all__ = [
    "collect_entities_by_type",
    "extract_nested_items",
    "to_dict",
    "walk_nested_entities",
]
