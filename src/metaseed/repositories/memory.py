"""In-memory entity repository implementation.

Wraps an entity tree (the editor's ``AppState``) as an EntityRepository for use
with EntityService. The tree is taken as the :class:`EntityTreeState` protocol,
not as an import of the UI's class, so the data layer stays independent of the
web app (ADR 004).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from metaseed.repositories.base import (
    EntityData,
    EntityRepository,
    EntityTreeNode,
    EntityTreeState,
)
from metaseed.repositories.helpers import (
    find_parent_ref_field,
    get_identifier_from_instance,
    normalize_reference_fields,
    update_parent_reference,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class MemoryEntityRepository(EntityRepository):
    """In-memory repository adapter for an entity tree.

    This adapter allows existing state-based code to work with the
    EntityService while providing a clean repository interface.
    """

    def __init__(
        self: Self,
        state: EntityTreeState,
        on_change: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize with the state to wrap.

        Args:
            state: The entity tree to wrap.
            on_change: Optional callback invoked with the state after each
                create/update/delete. The composition root wires this to the
                UI's ``auto_save`` so the data layer need not import the UI;
                its parameter is therefore typed by whoever wires it, not here.
        """
        self._state = state
        self._on_change = on_change

    def list_entities(self: Self, entity_type: str | None = None) -> list[EntityData]:
        """List all entities from the wrapped state."""
        result: list[EntityData] = []

        def collect(node: EntityTreeNode) -> None:
            if entity_type is None or node.entity_type == entity_type:
                data = {}
                if node.instance and hasattr(node.instance, "model_dump"):
                    data = node.instance.model_dump(mode="json", exclude_none=True)
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
        """Get an entity from the wrapped state."""
        node = self._state.nodes_by_id.get(entity_id)
        if not node:
            return None

        data = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(mode="json", exclude_none=True)

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
        """Create an entity in the wrapped state."""
        facade = self._state.get_or_create_facade()

        helper = facade.require_helper(entity_type)
        # `require_helper` resolves case-insensitively; adopt what it resolved.
        # Everything below — the parent-child check, the reference lookups,
        # storage and every later lookup — compares canonical spec names with
        # `==`, so keeping the caller's spelling rejected valid children and,
        # where the parent was mis-cased, mis-linked them without an error.
        entity_type = helper.name

        # Auto-detect parent from reference fields if not explicitly provided
        if not parent_id:
            parent_id = self._find_parent_from_references(helper, data)

        # Validate parent
        parent = None
        if parent_id:
            if parent_id not in self._state.nodes_by_id:
                raise ValueError(f"Parent entity not found: {parent_id}")
            parent = self._state.nodes_by_id[parent_id]

            # Validate parent-child relationship
            parent_helper = getattr(facade, parent.entity_type, None)
            if parent_helper:
                valid_child_types = list(parent_helper.child_fields.values())
                if entity_type not in valid_child_types:
                    raise ValueError(
                        f"Invalid parent: {parent.entity_type} cannot contain {entity_type}. "
                        f"Valid child types: {valid_child_types or 'none'}"
                    )

            # Auto-fill child's reference to parent
            ref_field = find_parent_ref_field(helper, parent.entity_type)
            if ref_field and ref_field not in data and parent_helper:
                parent_identifier = get_identifier_from_instance(
                    parent.instance, parent_helper
                )
                if parent_identifier:
                    data[ref_field] = parent_identifier

        # Normalize reference fields (convert embedded objects to IDs)
        data = normalize_reference_fields(data, helper, facade)

        instance = helper.create(**data)
        node = self._state.add_node(entity_type, instance, parent_id=parent_id)

        # Update parent's reference field
        if parent:
            self._update_parent_ref(facade, parent, node)

        if self._on_change is not None:
            self._on_change(self._state)

        return self._node_to_entity(node, include_children=False)

    def update_entity(self: Self, entity_id: str, data: dict[str, Any]) -> EntityData:
        """Update an entity in the wrapped state."""
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
            existing = node.instance.model_dump(mode="json", exclude_none=True)

        # Normalize reference fields in update data (convert embedded objects to IDs)
        data = normalize_reference_fields(data, helper, facade)

        merged = {**existing, **data}
        instance = helper.create(**merged)
        updated = self._state.update_node(entity_id, instance)

        if self._on_change is not None:
            self._on_change(self._state)

        # Serialize the post-update node; the original `node` still references
        # the pre-update instance and would return stale data.
        return self._node_to_entity(updated or node, include_children=False)

    def delete_entity(self: Self, entity_id: str) -> bool:
        """Delete an entity from the wrapped state."""
        result = self._state.delete_node(entity_id)
        if result and self._on_change is not None:
            self._on_change(self._state)
        return result

    def get_tree(self: Self) -> list[EntityData]:
        """Get the tree from the wrapped state."""
        return [self._node_to_entity(n) for n in self._state.entity_tree]

    def get_profile(self: Self) -> str:
        """Get the profile from the wrapped state."""
        return self._state.profile

    def get_version(self: Self) -> str | None:
        """Get the version from the wrapped state."""
        return self._state.version

    def set_profile(self: Self, profile: str, version: str | None = None) -> None:
        """Set the profile in the wrapped state."""
        self._state.profile = profile
        self._state.version = version
        self._state.facade = None

    def _node_to_entity(
        self: Self, node: EntityTreeNode, include_children: bool = True
    ) -> EntityData:
        """Convert a tree node to EntityData.

        Args:
            node: Tree node to convert.
            include_children: Whether to recursively include children.

        Returns:
            EntityData representation of the node.
        """
        data = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(mode="json", exclude_none=True)

        return EntityData(
            id=node.id,
            entity_type=node.entity_type,
            label=node.label,
            data=data,
            parent_id=node.parent_id,
            children=[self._node_to_entity(c) for c in node.children]
            if include_children
            else [],
        )

    def _find_parent_from_references(
        self: Self,
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
        parent_node: EntityTreeNode,
        child_node: EntityTreeNode,
    ) -> None:
        """Update parent's reference field to include child."""
        parent_data = {}
        if parent_node.instance and hasattr(parent_node.instance, "model_dump"):
            parent_data = parent_node.instance.model_dump(
                mode="json", exclude_none=True
            )

        child_data = {}
        if child_node.instance and hasattr(child_node.instance, "model_dump"):
            child_data = child_node.instance.model_dump(mode="json", exclude_none=True)

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
