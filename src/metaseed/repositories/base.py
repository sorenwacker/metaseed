"""Abstract repository interface for entity storage.

This module defines the abstract interface for entity CRUD operations,
following the same DI pattern as SpecPersistence/SpecProvider.
Implementations handle the actual storage mechanism (memory, filesystem, database).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityData:
    """Serializable entity data with hierarchy information.

    This is the transfer object between repository and consumers.
    It contains all information needed to reconstruct an entity and its
    position in the hierarchy.
    """

    id: str
    entity_type: str
    label: str
    data: dict[str, Any]
    parent_id: str | None = None
    children: list["EntityData"] = field(default_factory=list)


class EntityRepository(ABC):
    """Abstract interface for entity persistence.

    This interface defines the contract for entity CRUD operations,
    separating storage concerns from business logic. Implementations
    may use memory, filesystem, database, or other backends.

    The repository manages entities as a hierarchy (tree structure)
    where entities can have parent-child relationships.
    """

    @abstractmethod
    def list_entities(self, entity_type: str | None = None) -> list[EntityData]:
        """List all entities, optionally filtered by type.

        Args:
            entity_type: Optional filter by entity type.

        Returns:
            Flat list of all entities (not nested).
        """
        pass

    @abstractmethod
    def get_entity(self, entity_id: str) -> EntityData | None:
        """Get a single entity by ID.

        Args:
            entity_id: The entity's unique identifier.

        Returns:
            EntityData if found, None otherwise.
        """
        pass

    @abstractmethod
    def create_entity(
        self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str | None = None,
    ) -> EntityData:
        """Create a new entity.

        Args:
            entity_type: Type of entity (e.g., "Investigation", "Study").
            data: Entity field data as a dictionary.
            parent_id: Optional parent entity ID for hierarchy.

        Returns:
            Created EntityData with assigned ID.

        Raises:
            ValueError: If entity_type is unknown or parent not found.
        """
        pass

    @abstractmethod
    def update_entity(self, entity_id: str, data: dict[str, Any]) -> EntityData:
        """Update an existing entity.

        Args:
            entity_id: The entity's unique identifier.
            data: Fields to update (merged with existing data).

        Returns:
            Updated EntityData.

        Raises:
            ValueError: If entity not found.
        """
        pass

    @abstractmethod
    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and its children.

        Args:
            entity_id: The entity's unique identifier.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def get_tree(self) -> list[EntityData]:
        """Get the full entity tree with nested children.

        Returns:
            List of root entities with children populated recursively.
        """
        pass

    @abstractmethod
    def get_profile(self) -> str:
        """Get the current profile name.

        Returns:
            Profile name (e.g., "miappe", "isa").
        """
        pass

    @abstractmethod
    def get_version(self) -> str | None:
        """Get the current profile version.

        Returns:
            Version string or None for latest.
        """
        pass

    @abstractmethod
    def set_profile(self, profile: str, version: str | None = None) -> None:
        """Set the active profile and version.

        Args:
            profile: Profile name.
            version: Optional version, None for latest.
        """
        pass
