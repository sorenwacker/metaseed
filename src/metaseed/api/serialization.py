"""Serialization mixin for MetaseedClient.

Provides methods for serializing and loading entity data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

from metaseed.api.base import InstanceDataMixin

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade

__all__ = ["SerializationMixin", "SkippedNode"]


@dataclass(frozen=True)
class SkippedNode:
    """A tree-payload node that a permissive load dropped.

    This describes a node in the serialized payload, not a stored entity: the
    node was never created, so there is no ``EntityNode`` for it.

    Attributes:
        entity_type: The node's ``entity_type``, or None when it is absent or
            not a string.
        reason: Why the node could not be loaded.
        node: The raw payload node, including the subtree dropped with it, so a
            caller can report or recover it.
        descendants_dropped: How many nodes below this one were dropped with it.
    """

    entity_type: str | None
    reason: str
    node: Any
    descendants_dropped: int


def _count_descendants(node: Any) -> int:
    """Count the nodes below ``node`` in a tree payload."""
    if not isinstance(node, dict):
        return 0
    children = node.get("children")
    if not isinstance(children, list):
        return 0
    return sum(1 + _count_descendants(child) for child in children)


def _report_skip(
    on_skip: Callable[[SkippedNode], None], node: Any, reason: str
) -> None:
    """Report a dropped payload node and the subtree that goes with it.

    Args:
        on_skip: The caller's report sink.
        node: The raw payload node being dropped.
        reason: Why it could not be loaded.
    """
    entity_type = node.get("entity_type") if isinstance(node, dict) else None
    on_skip(
        SkippedNode(
            entity_type=entity_type if isinstance(entity_type, str) else None,
            reason=reason,
            node=node,
            descendants_dropped=_count_descendants(node),
        )
    )


class SerializationMixin(InstanceDataMixin):
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

    def load(
        self: Self,
        data: dict[str, Any],
        *,
        on_skip: Callable[[SkippedNode], None] | None = None,
    ) -> int:
        """Load entities from serialized data.

        Clears existing entities and loads from the provided data.
        Auto-detects format (flat with "entities" or nested "tree").

        Loading is strict by default: a tree node whose ``entity_type`` is
        missing or not defined by the profile aborts the load, so one bad node
        makes the whole dataset unreadable. Passing ``on_skip`` loads
        permissively instead — the callback both enables the mode and receives
        every dropped node, so a permissive load cannot discard data without
        telling the caller. A skipped node takes its subtree with it rather than
        re-parenting the orphans, which would assert a parent-child link the
        payload never stated.

        ``on_skip`` applies to the tree format; the flat format already drops
        entities it cannot reconstruct, with a warning log.

        Args:
            data: Serialized data from serialize() or entity list directly.
            on_skip: Called once per dropped node with a :class:`SkippedNode`.
                Omit it to keep the strict behavior.

        Returns:
            Number of entities loaded.

        Example:
            >>> with open("dataset.json") as f:
            ...     data = json.load(f)
            >>> client.load(data)  # auto-detects format
            >>> skipped = []
            >>> client.load(data, on_skip=skipped.append)  # permissive
        """
        if "tree" in data:
            return self._load_tree(data["tree"], on_skip)

        if "entities" in data:
            entities = data["entities"]
        else:
            entities = data if isinstance(data, list) else []

        return self._facade.load_from_dict(entities)

    def _load_tree(
        self: Self,
        tree: list[dict[str, Any]],
        on_skip: Callable[[SkippedNode], None] | None = None,
    ) -> int:
        """Load entities from nested tree format.

        Args:
            tree: The payload's root nodes.
            on_skip: Report sink enabling permissive loading, see :meth:`load`.

        Returns:
            Number of entities loaded.
        """
        self._facade.clear()
        count = 0

        def load_node(node: dict[str, Any], parent_id: str | None = None) -> None:
            nonlocal count
            if on_skip is not None:
                reason = self._unloadable_reason(node)
                if reason is not None:
                    _report_skip(on_skip, node, reason)
                    return

            try:
                created = self._facade.add_entity(
                    node["entity_type"],
                    node.get("data", {}),
                    node_id=node.get("id"),
                    parent_id=parent_id,
                    skip_validation=True,
                )
            except Exception as exc:
                if on_skip is None:
                    raise
                _report_skip(on_skip, node, f"could not be created: {exc}")
                return
            count += 1

            # Link children to the id the node was actually created under: a
            # node with no stored id gets a generated one, and passing the
            # absent stored id would orphan its whole subtree into roots.
            for child in self._node_list(node.get("children", []), on_skip, "children"):
                load_node(child, parent_id=created.id)

        for root in self._node_list(tree, on_skip, "tree"):
            load_node(root)

        return count

    def _unloadable_reason(self: Self, node: Any) -> str | None:
        """Say why a tree node cannot be loaded, or None if it can.

        Args:
            node: A node from the tree payload.

        Returns:
            A human-readable reason, or None when the node names an entity type
            this profile defines.
        """
        if not isinstance(node, dict):
            return "node is not a mapping"
        entity_type = node.get("entity_type")
        if not isinstance(entity_type, str) or not entity_type.strip():
            return "node has no 'entity_type'"
        if self._facade.get_helper(entity_type) is None:
            return f"unknown entity type '{entity_type}'"
        return None

    @staticmethod
    def _node_list(
        value: Any, on_skip: Callable[[SkippedNode], None] | None, key: str
    ) -> Any:
        """Return a payload's list of nodes, reporting a malformed one.

        Args:
            value: The payload's ``tree`` or a node's ``children``.
            on_skip: Report sink enabling permissive loading, see :meth:`load`.
            key: Which key ``value`` came from, for the report.

        Returns:
            ``value`` unchanged, except when permissive and it is not a list:
            then it is reported and replaced with an empty list.
        """
        if isinstance(value, list) or on_skip is None:
            return value
        on_skip(
            SkippedNode(
                entity_type=None,
                reason=f"'{key}' is not a list of nodes",
                node=value,
                descendants_dropped=0,
            )
        )
        return []

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
