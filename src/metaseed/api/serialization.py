"""Serialization mixin for MetaseedClient.

Provides methods for serializing and loading entity data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade


class SerializationMixin:
    """Mixin providing serialization capabilities for MetaseedClient."""

    _facade: ProfileFacade

    def serialize(self: Self, format: str = "flat") -> dict[str, Any]:
        """Serialize all entities to a dictionary.

        Returns a structure that can be saved to JSON/YAML and later
        loaded back with load().

        Args:
            format: Output format - "flat" (default) or "tree".
                - "flat": List of entities with _type and _parent_unique_id
                - "tree": Nested hierarchy with id, entity_type, label,
                  data, children

        Returns:
            Dictionary with profile info and entity data.

        Example:
            >>> data = client.serialize()  # flat format
            >>> data = client.serialize(format="tree")  # nested tree
            >>> with open("dataset.json", "w") as f:
            ...     json.dump(data, f)
        """
        base: dict[str, Any] = {
            "profile": self._facade.profile,
            "version": self._facade.version,
        }

        if format == "tree":
            base["tree"] = self._serialize_tree()
        else:
            base["entities"] = self._facade.to_dict()

        return base

    def _serialize_tree(self: Self) -> list[dict[str, Any]]:
        """Serialize entities as nested tree structure."""
        roots = self._facade.get_roots()

        def node_to_tree(node: Any) -> dict[str, Any]:
            data = self._get_instance_data(node.instance)

            helper = self._facade.get_helper(node.entity_type)
            if helper and node.instance:
                label = helper.get_label(node.instance)
            else:
                label = node.label

            return {
                "id": node.id,
                "entity_type": node.entity_type,
                "label": label,
                "data": data,
                "children": [node_to_tree(c) for c in node.children],
            }

        return [node_to_tree(r) for r in roots]

    def load(self: Self, data: dict[str, Any]) -> int:
        """Load entities from serialized data.

        Clears existing entities and loads from the provided data.
        Auto-detects format (flat with "entities" or nested "tree").

        Args:
            data: Serialized data from serialize() or entity list directly.

        Returns:
            Number of entities loaded.

        Example:
            >>> with open("dataset.json") as f:
            ...     data = json.load(f)
            >>> client.load(data)  # auto-detects format
        """
        if "tree" in data:
            return self._load_tree(data["tree"])

        if "entities" in data:
            entities = data["entities"]
        else:
            entities = data if isinstance(data, list) else []

        return self._facade.load_from_dict(entities)

    def _load_tree(self: Self, tree: list[dict[str, Any]]) -> int:
        """Load entities from nested tree format."""
        self._facade.clear()
        count = 0

        def load_node(node: dict[str, Any], parent_id: str | None = None) -> None:
            nonlocal count
            entity_type = node["entity_type"]
            data = node.get("data", {})
            node_id = node.get("id")

            self._facade.add_entity(
                entity_type,
                data,
                node_id=node_id,
                parent_id=parent_id,
                skip_validation=True,
            )
            count += 1

            for child in node.get("children", []):
                load_node(child, parent_id=node_id)

        for root in tree:
            load_node(root)

        return count

    def load_yaml(self: Self, path: str) -> int:
        """Load entities from a YAML dataset file.

        Args:
            path: Path to the YAML file containing entity data.

        Returns:
            Number of entities loaded.

        Example:
            >>> client.load_yaml("my-dataset.yaml")
        """
        return self._facade.load_yaml(path)

    def clear(self: Self) -> None:
        """Clear all entities from the client."""
        self._facade.clear()

    def _get_instance_data(self: Self, instance: Any) -> dict[str, Any]:
        """Extract data dictionary from a model instance.

        Args:
            instance: Pydantic model instance or None.

        Returns:
            Data dictionary or empty dict if instance is None/invalid.
        """
        if instance and hasattr(instance, "model_dump"):
            result: dict[str, Any] = instance.model_dump(mode="json", exclude_none=True)
            return result
        return {}
