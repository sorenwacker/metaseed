"""Entity service - single source of truth for entity operations.

All entity CRUD operations go through this service.
Both UI routes and MCP tools use this service via dependency injection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Self

from metaseed.repositories.base import EntityData, EntityRepository
from metaseed.repositories.memory import MemoryEntityRepository

if TYPE_CHECKING:
    from metaseed.ui.state import AppState

logger = logging.getLogger(__name__)

# Backwards compatibility alias
AppStateAdapter = MemoryEntityRepository


class EntityService:
    """Service for entity operations with repository-based storage.

    This service provides a unified API for entity CRUD operations.
    It uses dependency injection to support different storage backends
    (memory, file, database) via the EntityRepository interface.
    """

    def __init__(self: Self, repository: EntityRepository) -> None:
        """Initialize with a repository.

        Args:
            repository: EntityRepository implementation for storage.
        """
        self._repo = repository

    @property
    def repository(self: Self) -> EntityRepository:
        """Get the underlying repository."""
        return self._repo

    def list_entities(self: Self, entity_type: str | None = None) -> dict[str, Any]:
        """List all entities.

        Args:
            entity_type: Optional filter by type.

        Returns:
            Dict with profile, version, entities by type, and total count.
        """
        entities = self._repo.list_entities(entity_type)

        # Group by type
        by_type: dict[str, list] = {}
        for e in entities:
            if e.entity_type not in by_type:
                by_type[e.entity_type] = []
            by_type[e.entity_type].append(
                {
                    "id": e.id,
                    "label": e.label,
                    "data": e.data,
                }
            )

        return {
            "profile": self._repo.get_profile(),
            "version": self._repo.get_version(),
            "entities": by_type,
            "total": len(entities),
        }

    def get_entity(self: Self, entity_id: str) -> dict[str, Any] | None:
        """Get entity by ID.

        Args:
            entity_id: Entity ID.

        Returns:
            Entity data or None if not found.
        """
        entity = self._repo.get_entity(entity_id)
        if not entity:
            return None

        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "label": entity.label,
            "parent_id": entity.parent_id,
            "data": entity.data,
        }

    def create_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new entity.

        Args:
            entity_type: Type of entity to create.
            data: Entity field data.
            parent_id: Optional parent entity ID.

        Returns:
            Created entity info.

        Raises:
            ValueError: If entity type unknown or parent not found.
        """
        entity = self._repo.create_entity(entity_type, data, parent_id)

        result = {
            "status": "created",
            "id": entity.id,
            "entity_type": entity.entity_type,
            "label": entity.label,
        }

        if parent_id:
            result["parent_id"] = parent_id
            parent = self._repo.get_entity(parent_id)
            if parent:
                result["parent_type"] = parent.entity_type

        self._notify_change("created", entity)
        return result

    def update_entity(self: Self, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing entity.

        Args:
            entity_id: Entity ID.
            data: Fields to update (merged with existing).

        Returns:
            Updated entity info.

        Raises:
            ValueError: If entity not found.
        """
        entity = self._repo.update_entity(entity_id, data)

        self._notify_change("updated", entity)

        return {
            "status": "updated",
            "id": entity.id,
            "entity_type": entity.entity_type,
            "label": entity.label,
        }

    def delete_entity(self: Self, entity_id: str) -> dict[str, Any]:
        """Delete an entity.

        Args:
            entity_id: Entity ID.

        Returns:
            Deletion status.

        Raises:
            ValueError: If entity not found.
        """
        entity = self._repo.get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        entity_type = entity.entity_type
        label = entity.label

        self._repo.delete_entity(entity_id)

        self._notify_change("deleted", entity)

        return {
            "status": "deleted",
            "entity_type": entity_type,
            "label": label,
        }

    def get_tree(self: Self) -> dict[str, Any]:
        """Get entity tree structure.

        Returns:
            Tree with nested children.
        """
        tree = self._repo.get_tree()

        def entity_to_dict(e: EntityData) -> dict:
            return {
                "id": e.id,
                "entity_type": e.entity_type,
                "label": e.label,
                "has_children": bool(e.children),
                "children": [entity_to_dict(c) for c in e.children],
            }

        tree_data = [entity_to_dict(e) for e in tree]

        return {
            "profile": self._repo.get_profile(),
            "tree": tree_data,
            "root_count": len(tree),
            "total_count": len(self._repo.list_entities()),
        }

    def _notify_change(self: Self, event: str, entity: EntityData) -> None:
        """Notify listeners of entity changes.

        Args:
            event: Event type (created, updated, deleted).
            entity: The affected entity.
        """
        try:
            from metaseed.ui.websocket import notify_state_changed

            notify_state_changed(
                event=event,
                entity_type=entity.entity_type,
                entity_id=entity.id,
            )
        except ImportError:
            pass


# Backwards compatibility layer for existing code
# These module-level functions wrap a global service instance

_service: EntityService | None = None
_state: AppState | None = None


def set_state(state: AppState) -> None:
    """Set the global state reference (backwards compatibility).

    Creates a MemoryEntityRepository to use AppState with EntityService.
    """
    global _state, _service
    _state = state
    _service = EntityService(MemoryEntityRepository(state))
    logger.info("Entity service: initialized with memory repository")


def set_service(service: EntityService) -> None:
    """Set the global service instance."""
    global _service
    _service = service
    logger.info("Entity service: initialized with custom repository")


def get_service() -> EntityService:
    """Get the global service instance."""
    if _service is None:
        raise RuntimeError("Entity service not initialized")
    return _service


def get_state() -> AppState:
    """Get the global state (backwards compatibility)."""
    if _state is None:
        raise RuntimeError("Entity service not initialized - call set_state first")
    return _state


def list_entities(entity_type: str | None = None) -> dict[str, Any]:
    """List all entities (backwards compatibility)."""
    return get_service().list_entities(entity_type)


def get_entity(node_id: str) -> dict[str, Any] | None:
    """Get entity by ID (backwards compatibility)."""
    return get_service().get_entity(node_id)


def create_entity(
    entity_type: str,
    data: dict[str, Any],
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Create a new entity (backwards compatibility)."""
    return get_service().create_entity(entity_type, data, parent_id)


def update_entity(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update an existing entity (backwards compatibility)."""
    return get_service().update_entity(node_id, data)


def delete_entity(node_id: str) -> dict[str, Any]:
    """Delete an entity (backwards compatibility)."""
    return get_service().delete_entity(node_id)


def get_tree() -> dict[str, Any]:
    """Get entity tree structure (backwards compatibility)."""
    return get_service().get_tree()
