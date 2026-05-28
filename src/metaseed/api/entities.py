"""Public API entity types for metaseed.

This module provides clean domain objects for entities and entity nodes.
These types provide a stable public interface that wraps internal types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Entity:
    """A metadata entity instance.

    Clean public representation of an entity with its data and metadata.
    Wraps internal entity representations to provide a stable API.

    Attributes:
        id: Unique identifier for this entity instance.
        entity_type: Type of entity (e.g., "Investigation", "Study").
        data: Entity field values as a dictionary.
        parent_id: ID of parent entity if this entity has a parent.
    """

    id: str
    entity_type: str
    data: dict[str, Any]
    parent_id: str | None = None

    @property
    def label(self) -> str:
        """Derive a display label from entity data.

        Uses the first non-empty string value from the data.
        """
        for value in self.data.values():
            if isinstance(value, str) and value:
                return str(value)[:50]
        return f"New {self.entity_type}"

    def get(self, field: str, default: Any = None) -> Any:
        """Get a field value from the entity data.

        Args:
            field: Field name to retrieve.
            default: Value to return if field not present.

        Returns:
            Field value or default.
        """
        return self.data.get(field, default)

    def __getitem__(self, field: str) -> Any:
        """Get a field value using subscript notation.

        Args:
            field: Field name to retrieve.

        Returns:
            Field value.

        Raises:
            KeyError: If field not found.
        """
        return self.data[field]


@dataclass(slots=True)
class EntityNode:
    """A node in the entity tree.

    Represents an entity with its hierarchical position and children.
    Used for tree visualization and navigation.

    Attributes:
        id: Unique identifier for this node.
        entity_type: Type of entity.
        label: Display label for the node.
        has_children: Whether this node has children.
        children: List of child nodes (lazy-loaded in some contexts).
    """

    id: str
    entity_type: str
    label: str
    has_children: bool = False
    children: list[EntityNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert node to dictionary for serialization.

        Returns:
            Dictionary representation of the node tree.
        """
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "label": self.label,
            "has_children": self.has_children,
            "children": [c.to_dict() for c in self.children],
        }
