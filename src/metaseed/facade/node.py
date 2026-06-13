"""Entity node representation for the entity graph.

This module defines the EntityNode dataclass used to represent entity
instances and their relationships in the profile facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["IDENTIFIER_FIELDS", "EntityNode"]

# Common identifier field names used for indexing and reference lookups
IDENTIFIER_FIELDS = ("alias", "unique_id", "identifier")


@dataclass
class EntityNode:
    """A node in the entity graph.

    Represents an entity instance with its position in the hierarchy.
    Parent relationships are derived from reference fields in the entity data.

    Attributes:
        id: Unique node identifier (UUID or provided ID).
        entity_type: Type of entity (e.g., "Study", "Sample").
        instance: The Pydantic model instance.
        parent_id: ID of parent node, derived from reference fields.
    """

    id: str
    entity_type: str
    instance: Any
    parent_id: str | None = None
    children: list[EntityNode] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Derive display label from instance data.

        Uses the first field value by convention (see specs docs).
        """
        if self.instance and hasattr(self.instance, "model_dump"):
            data = self.instance.model_dump(exclude_none=True)
        elif isinstance(self.instance, dict):
            data = self.instance
        else:
            return f"New {self.entity_type}"

        # derive_label needs spec, but we don't have it here
        # Use simple fallback: first non-empty string value
        for value in data.values():
            if isinstance(value, str) and value:
                return str(value)[:50]

        return f"New {self.entity_type}"
