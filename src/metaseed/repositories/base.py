"""Abstract repository interface for entity storage.

This module defines the abstract interface for entity CRUD operations,
following the same DI pattern as SpecPersistence/SpecProvider.
Implementations handle the actual storage mechanism (memory, filesystem, database).

It also defines the shape of the in-memory entity tree a repository may wrap
(:class:`EntityTreeState`, :class:`EntityTreeNode`). These are protocols rather
than imports of the editor's ``AppState`` and ``TreeNode``: the data layer
describes what it needs and the host supplies something that fits, so the
dependency points at the core instead of at the web app (ADR 004).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


class EntityTreeNode(Protocol):
    """One node of an in-memory entity tree.

    Attributes:
        id: Node identifier, unique within the tree.
        entity_type: Entity type name (e.g. "Investigation").
        label: Human-readable label derived from the instance.
        instance: The entity instance (a generated Pydantic model).
        parent_id: Identifier of the parent node, or None for a root.
    """

    id: str
    entity_type: str
    label: str
    instance: Any
    parent_id: str | None

    @property
    def children(self) -> Sequence["EntityTreeNode"]:
        """The node's child nodes."""
        ...


class EntityTreeState(Protocol):
    """The entity tree a memory-backed repository reads and writes.

    Only the members a repository actually uses are declared, so a host is free
    to carry whatever else its own session needs.

    Attributes:
        profile: Active profile name.
        version: Active profile version, or None for latest.
        facade: The ProfileFacade backing the tree; set to None to force a
            rebuild after a profile change. Typed loosely to keep the data
            layer independent of the facade's import.
    """

    profile: str
    version: str | None
    facade: Any

    @property
    def entity_tree(self) -> Sequence[EntityTreeNode]:
        """Root nodes of the tree."""
        ...

    @property
    def nodes_by_id(self) -> Mapping[str, EntityTreeNode]:
        """Every node in the tree, indexed by identifier."""
        ...

    def get_or_create_facade(self) -> Any:
        """The ProfileFacade for the active profile, created if needed."""
        ...

    def add_node(
        self, entity_type: str, instance: Any, parent_id: str | None = None
    ) -> EntityTreeNode:
        """Add an entity to the tree and return the node created for it."""
        ...

    def update_node(self, node_id: str, instance: Any) -> EntityTreeNode | None:
        """Replace a node's instance, returning the updated node or None."""
        ...

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its children, returning whether it existed."""
        ...


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
