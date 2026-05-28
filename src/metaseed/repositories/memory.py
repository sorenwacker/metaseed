"""In-memory entity repository implementation.

Wraps AppState as an EntityRepository for use with EntityService.
This allows existing AppState-based code to work with the unified API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from metaseed.repositories.base import EntityData, EntityRepository
from metaseed.repositories.helpers import (
    find_parent_ref_field,
    get_identifier_from_instance,
    normalize_reference_fields,
    update_parent_reference,
)

if TYPE_CHECKING:
    from metaseed.ui.state import AppState, TreeNode


class MemoryEntityRepository(EntityRepository):
    """In-memory repository adapter for AppState.

    This adapter allows existing AppState-based code to work with the
    EntityService while providing a clean repository interface.
    """

    def __init__(self: Self, state: AppState) -> None:
        """Initialize with AppState.

        Args:
            state: The AppState instance to wrap.
        """
        self._state = state

    def list_entities(self: Self, entity_type: str | None = None) -> list[EntityData]:
        """List all entities from AppState."""
        result: list[EntityData] = []

        def collect(node: TreeNode) -> None:
            if entity_type is None or node.entity_type == entity_type:
                data = {}
                if node.instance and hasattr(node.instance, "model_dump"):
                    data = node.instance.model_dump(exclude_none=True)
                result.append(
                    EntityData(
                        id=node.id,
                        entity_type=node.entity_type,
                        label=node.label,
                        data=data,
                        parent_id=node.parent_id,
                    )
                )
            for child in node.children:
                collect(child)

        for node in self._state.entity_tree:
            collect(node)

        return result

    def get_entity(self: Self, entity_id: str) -> EntityData | None:
        """Get entity from AppState."""
        node = self._state.nodes_by_id.get(entity_id)
        if not node:
            return None

        data = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)

        return EntityData(
            id=node.id,
            entity_type=node.entity_type,
            label=node.label,
            data=data,
            parent_id=node.parent_id,
            children=[self._node_to_entity(c) for c in node.children],
        )

    def create_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str | None = None,
    ) -> EntityData:
        """Create entity in AppState."""
        from metaseed.ui.datasets import auto_save

        facade = self._state.get_or_create_facade()

        helper = getattr(facade, entity_type, None)
        if not helper:
            raise ValueError(f"Unknown entity type: {entity_type}")

        # Auto-detect parent from reference fields if not explicitly provided
        if not parent_id:
            parent_id = self._find_parent_from_references(facade, helper, data)

        # Validate parent
        parent = None
        if parent_id:
            if parent_id not in self._state.nodes_by_id:
                raise ValueError(f"Parent entity not found: {parent_id}")
            parent = self._state.nodes_by_id[parent_id]

            # Validate parent-child relationship
            parent_helper = getattr(facade, parent.entity_type, None)
            if parent_helper:
                valid_child_types = list(parent_helper.nested_fields.values())
                if entity_type not in valid_child_types:
                    raise ValueError(
                        f"Invalid parent: {parent.entity_type} cannot contain {entity_type}. "
                        f"Valid child types: {valid_child_types or 'none'}"
                    )

            # Auto-fill child's reference to parent
            ref_field = find_parent_ref_field(helper, parent.entity_type)
            if ref_field and ref_field not in data and parent_helper:
                parent_identifier = get_identifier_from_instance(parent.instance, parent_helper)
                if parent_identifier:
                    data[ref_field] = parent_identifier

        # Normalize reference fields (convert embedded objects to IDs)
        data = normalize_reference_fields(data, helper, facade)

        instance = helper.create(**data)
        node = self._state.add_node(entity_type, instance, parent_id=parent_id)

        # Update parent's reference field
        if parent:
            self._update_parent_ref(facade, parent, node)

        auto_save(self._state)

        validated_data = instance.model_dump(exclude_none=True)
        return EntityData(
            id=node.id,
            entity_type=entity_type,
            label=node.label,
            data=validated_data,
            parent_id=parent_id,
        )

    def update_entity(self: Self, entity_id: str, data: dict[str, Any]) -> EntityData:
        """Update entity in AppState."""
        from metaseed.ui.datasets import auto_save

        node = self._state.nodes_by_id.get(entity_id)
        if not node:
            raise ValueError(f"Entity not found: {entity_id}")

        facade = self._state.get_or_create_facade()
        helper = getattr(facade, node.entity_type, None)
        if not helper:
            raise ValueError(f"Unknown entity type: {node.entity_type}")

        # Merge data
        existing = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            existing = node.instance.model_dump(exclude_none=True)

        # Normalize reference fields in update data (convert embedded objects to IDs)
        data = normalize_reference_fields(data, helper, facade)

        merged = {**existing, **data}
        instance = helper.create(**merged)
        self._state.update_node(entity_id, instance)

        auto_save(self._state)

        validated_data = instance.model_dump(exclude_none=True)
        return EntityData(
            id=node.id,
            entity_type=node.entity_type,
            label=node.label,
            data=validated_data,
            parent_id=node.parent_id,
        )

    def delete_entity(self: Self, entity_id: str) -> bool:
        """Delete entity from AppState."""
        from metaseed.ui.datasets import auto_save

        result = self._state.delete_node(entity_id)
        if result:
            auto_save(self._state)
        return result

    def get_tree(self: Self) -> list[EntityData]:
        """Get tree from AppState."""
        return [self._node_to_entity(n) for n in self._state.entity_tree]

    def get_profile(self: Self) -> str:
        """Get profile from AppState."""
        return self._state.profile

    def get_version(self: Self) -> str | None:
        """Get version from AppState."""
        return self._state.version

    def set_profile(self: Self, profile: str, version: str | None = None) -> None:
        """Set profile in AppState."""
        self._state.profile = profile
        self._state.version = version
        self._state.facade = None

    def _node_to_entity(self: Self, node: TreeNode) -> EntityData:
        """Convert TreeNode to EntityData."""
        data = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)

        return EntityData(
            id=node.id,
            entity_type=node.entity_type,
            label=node.label,
            data=data,
            parent_id=node.parent_id,
            children=[self._node_to_entity(c) for c in node.children],
        )

    def _find_parent_from_references(
        self: Self,
        _facade: Any,
        helper: Any,
        data: dict[str, Any],
    ) -> str | None:
        """Auto-detect parent from reference fields in data.

        Looks at the entity's reference fields and finds matching parent entities.
        """
        for field_name, (target_type, target_field) in helper.reference_fields.items():
            ref_value = data.get(field_name)
            if not ref_value:
                continue

            # Search for entity with matching identifier
            for node in self._state.nodes_by_id.values():
                if node.entity_type != target_type:
                    continue

                node_data = node.instance.model_dump() if node.instance else {}
                if node_data.get(target_field) == ref_value:
                    return node.id

        return None

    def _update_parent_ref(
        self: Self,
        facade: Any,
        parent_node: TreeNode,
        child_node: TreeNode,
    ) -> None:
        """Update parent's reference field to include child."""
        parent_data = {}
        if parent_node.instance and hasattr(parent_node.instance, "model_dump"):
            parent_data = parent_node.instance.model_dump(exclude_none=True)

        child_data = {}
        if child_node.instance and hasattr(child_node.instance, "model_dump"):
            child_data = child_node.instance.model_dump(exclude_none=True)

        updated_field = update_parent_reference(
            facade,
            parent_data,
            parent_node.entity_type,
            child_data,
            child_node.entity_type,
            child_node.id,
        )

        if updated_field:
            # Recreate parent instance with updated data
            parent_helper = getattr(facade, parent_node.entity_type, None)
            if parent_helper:
                new_instance = parent_helper.create(**parent_data)
                self._state.update_node(parent_node.id, new_instance)


# Backwards compatibility alias
AppStateAdapter = MemoryEntityRepository
