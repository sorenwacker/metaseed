"""UI state management classes.

Contains dataclasses for managing application state, tree nodes,
and nested editing context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade
    from metaseed.ui.spec_builder import SpecBuilderState


def _get_default_profile() -> str:
    """Get the default profile using ProfileFactory."""
    from metaseed.profiles import ProfileFactory

    return ProfileFactory().get_default_profile()


@dataclass
class TreeNode:
    """A node in the entity tree."""

    id: str
    entity_type: str
    instance: Any
    label: str
    children: list[TreeNode] = field(default_factory=list)
    parent_id: str | None = None

    @classmethod
    def create(
        cls,
        entity_type: str,
        instance: Any,
        parent_id: str | None = None,
        node_id: str | None = None,
    ) -> TreeNode:
        """Create a new tree node from an entity instance.

        Args:
            entity_type: Type of entity.
            instance: The entity instance (Pydantic model).
            parent_id: Optional parent node ID.
            node_id: Optional node ID to preserve (for loading saved datasets).
                    If not provided, a new UUID is generated.
        """
        from metaseed.repositories.helpers import derive_label

        data = instance.model_dump() if hasattr(instance, "model_dump") else {}
        label = derive_label(entity_type, data)

        return cls(
            id=node_id or str(uuid.uuid4())[:8],
            entity_type=entity_type,
            instance=instance,
            label=label,
            parent_id=parent_id,
        )

    def to_dict(self) -> dict:
        """Convert node to dictionary for template rendering."""
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "label": self.label,
            "has_children": bool(self.children),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class NestedEditContext:
    """Context for editing a nested item."""

    field_name: str  # The field containing this item (e.g., "studies")
    row_idx: int  # Index in the parent's list
    entity_type: str  # Entity type being edited (e.g., "Study")
    parent_entity_type: str  # Parent entity type (e.g., "Investigation")
    nested_items: dict[str, list] = field(default_factory=dict)  # This item's nested fields


@dataclass
class AppState:
    """Server-side state for the UI."""

    profile: str = field(default_factory=_get_default_profile)
    version: str | None = None  # None means use latest
    facade: ProfileFacade | None = None
    entity_tree: list[TreeNode] = field(default_factory=list)
    nodes_by_id: dict[str, TreeNode] = field(default_factory=dict)
    editing_node_id: str | None = None
    current_nested_items: dict[str, list] = field(default_factory=dict)
    nested_edit_stack: list[NestedEditContext] = field(default_factory=list)  # Navigation stack
    spec_builder: SpecBuilderState | None = None  # Spec Builder state

    def get_or_create_facade(self: Self) -> ProfileFacade:
        """Get existing facade or create new one."""
        from metaseed.facade import ProfileFacade

        if self.facade is None or self.facade.profile != self.profile:
            self.facade = ProfileFacade(self.profile, self.version)
        return self.facade

    def get_root_entity_types(self: Self) -> list[str]:
        """Get entity types that can be created at root level.

        Returns the profile's declared root_entity (typically Investigation).
        Uses the facade's injected spec if available, otherwise loads from disk.
        """
        from metaseed.specs.loader import SpecLoadError

        facade = self.get_or_create_facade()

        # Use injected spec from facade if available
        if facade._spec is not None:
            root = facade._spec.root_entity
            if root and root in facade.entities:
                return [root]
        else:
            # Fall back to loading from disk
            try:
                spec = facade._loader.load_profile(version=facade.version, profile=self.profile)
                root = spec.root_entity
                if root and root in facade.entities:
                    return [root]
            except SpecLoadError:
                pass

        # Fallback to Investigation if available
        if "Investigation" in facade.entities:
            return ["Investigation"]

        return []

    def add_node(
        self: Self,
        entity_type: str,
        instance: Any,
        parent_id: str | None = None,
        node_id: str | None = None,
    ) -> TreeNode:
        """Add a new node to the tree.

        Args:
            entity_type: Type of entity.
            instance: The entity instance.
            parent_id: Optional parent node ID for hierarchy.
            node_id: Optional node ID to preserve (for loading saved datasets).
        """
        node = TreeNode.create(entity_type, instance, parent_id, node_id)
        self.nodes_by_id[node.id] = node

        if parent_id and parent_id in self.nodes_by_id:
            self.nodes_by_id[parent_id].children.append(node)
        else:
            self.entity_tree.append(node)

        return node

    def update_node(self: Self, node_id: str, instance: Any) -> TreeNode | None:
        """Update an existing node."""
        from metaseed.repositories.helpers import derive_label

        node = self.nodes_by_id.get(node_id)
        if node:
            node.instance = instance
            if hasattr(instance, "model_dump"):
                data = instance.model_dump()
                node.label = derive_label(node.entity_type, data)
        return node

    def delete_node(self: Self, node_id: str) -> bool:
        """Delete a node and all its children."""
        node = self.nodes_by_id.get(node_id)
        if not node:
            return False

        def remove_recursively(n: TreeNode) -> None:
            for child in n.children:
                remove_recursively(child)
            self.nodes_by_id.pop(n.id, None)

        if node.parent_id and node.parent_id in self.nodes_by_id:
            parent = self.nodes_by_id[node.parent_id]
            parent.children = [c for c in parent.children if c.id != node.id]
        else:
            self.entity_tree = [n for n in self.entity_tree if n.id != node.id]

        remove_recursively(node)

        if self.editing_node_id == node_id:
            self.editing_node_id = None

        return True

    def get_tree_data(self: Self) -> list[dict]:
        """Get tree data for template rendering using TreeNode hierarchy."""

        def node_to_dict(node: TreeNode) -> dict:
            """Convert TreeNode to dict recursively including children."""
            result = {
                "id": node.id,
                "entity_type": node.entity_type,
                "label": node.label,
                "has_children": bool(node.children),
                "children": [node_to_dict(child) for child in node.children],
            }
            return result

        return [node_to_dict(n) for n in self.entity_tree]

    def reset(self: Self) -> None:
        """Reset all state."""
        self.entity_tree = []
        self.nodes_by_id = {}
        self.editing_node_id = None
        self.current_nested_items = {}
        self.nested_edit_stack = []
