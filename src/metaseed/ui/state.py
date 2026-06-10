"""UI state management classes.

Contains dataclasses for managing application state, tree nodes,
and nested editing context.

AppState now delegates entity storage to ProfileFacade while maintaining
UI-specific state (editing_node_id, current_nested_items, etc.).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from metaseed.facade import EntityNode, ProfileFacade
    from metaseed.ui.spec_builder import SpecBuilderState


def _get_default_profile() -> str:
    """Get the default profile using ProfileFactory."""
    from metaseed.profiles import ProfileFactory

    return ProfileFactory().get_default_profile()


@dataclass
class TreeNode:
    """A node in the entity tree.

    Note: This class is maintained for backward compatibility with existing
    UI code. New code should use EntityNode from facade.py directly.
    TreeNode wraps EntityNode to provide the same interface.
    """

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
        spec: Any = None,
    ) -> TreeNode:
        """Create a new tree node from an entity instance.

        Args:
            entity_type: Type of entity.
            instance: The entity instance (Pydantic model).
            parent_id: Optional parent node ID.
            node_id: Optional node ID to preserve (for loading saved datasets).
                    If not provided, a new UUID is generated.
            spec: Optional EntityDefSpec for label derivation.
        """
        from metaseed.repositories.helpers import derive_label

        data = instance.model_dump() if hasattr(instance, "model_dump") else {}
        label = derive_label(entity_type, data, spec)

        return cls(
            id=node_id or str(uuid.uuid4())[:8],
            entity_type=entity_type,
            instance=instance,
            label=label,
            parent_id=parent_id,
        )

    @classmethod
    def from_entity_node(
        cls, entity_node: EntityNode, facade: ProfileFacade
    ) -> TreeNode:
        """Create TreeNode from EntityNode for backward compatibility.

        Args:
            entity_node: The EntityNode to wrap.
            facade: ProfileFacade for label derivation.

        Returns:
            TreeNode wrapping the EntityNode.
        """
        helper = getattr(facade, entity_node.entity_type, None)
        if helper and entity_node.instance:
            label = helper.get_label(entity_node.instance)
        else:
            label = entity_node.label

        node = cls(
            id=entity_node.id,
            entity_type=entity_node.entity_type,
            instance=entity_node.instance,
            label=label,
            parent_id=entity_node.parent_id,
        )

        # Recursively convert children
        for child_entity_node in entity_node.children:
            node.children.append(cls.from_entity_node(child_entity_node, facade))

        return node

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
    nested_items: dict[str, list] = field(
        default_factory=dict
    )  # This item's nested fields


@dataclass
class AppState:
    """Server-side state for the UI.

    AppState now delegates entity storage to ProfileFacade while maintaining
    UI-specific state. This enables the facade to be the single source of truth
    for entity data, usable across UI, CLI, MCP, and JupyterLab.

    Storage delegation:
    - Entity instances are stored in facade._instances (EntityNode objects)
    - nodes_by_id and entity_tree provide TreeNode wrappers for backward compat
    - Parent-child relationships are managed by facade

    UI-only state:
    - editing_node_id: Currently selected node for editing
    - current_nested_items: Form editing state for nested entities
    - nested_edit_stack: Navigation stack for nested entity editing
    - spec_builder: Spec Builder UI state
    """

    profile: str = field(default_factory=_get_default_profile)
    version: str | None = None  # None means use latest
    facade: ProfileFacade | None = None

    # UI-only state (not delegated to facade)
    editing_node_id: str | None = None
    current_nested_items: dict[str, list] = field(default_factory=dict)
    nested_edit_stack: list[NestedEditContext] = field(default_factory=list)
    spec_builder: SpecBuilderState | None = None

    # TreeNode caches for backward compatibility
    _tree_cache: list[TreeNode] = field(default_factory=list)
    _nodes_cache: dict[str, TreeNode] = field(default_factory=dict)
    _cache_valid: bool = field(default=False)

    def invalidate_cache(self: Self) -> None:
        """Invalidate the TreeNode cache.

        Call this after modifying entities via MetaseedClient or facade
        to ensure the tree cache is rebuilt on next access.
        """
        self._cache_valid = False

    # Alias for backward compatibility
    _invalidate_cache = invalidate_cache

    def _rebuild_cache(self: Self) -> None:
        """Rebuild TreeNode cache from facade's EntityNodes."""
        if self._cache_valid:
            return

        self._tree_cache = []
        self._nodes_cache = {}

        facade = self.get_or_create_facade()
        if not facade._instances:
            self._cache_valid = True
            return

        # Build TreeNodes from EntityNodes
        for root_entity_node in facade.get_roots():
            tree_node = TreeNode.from_entity_node(root_entity_node, facade)
            self._tree_cache.append(tree_node)
            self._index_tree_node(tree_node)

        self._cache_valid = True

    def _index_tree_node(self: Self, node: TreeNode) -> None:
        """Index a TreeNode and its children."""
        self._nodes_cache[node.id] = node
        for child in node.children:
            self._index_tree_node(child)

    @property
    def entity_tree(self: Self) -> list[TreeNode]:
        """Get root TreeNodes (backward compatible property).

        Returns TreeNode wrappers around facade's EntityNodes.
        """
        self._rebuild_cache()
        return self._tree_cache

    @entity_tree.setter
    def entity_tree(self: Self, value: list[TreeNode]) -> None:
        """Set entity tree (for backward compatibility during reset)."""
        self._tree_cache = value
        self._nodes_cache = {}
        for node in value:
            self._index_tree_node(node)
        self._cache_valid = True

    @property
    def nodes_by_id(self: Self) -> dict[str, TreeNode]:
        """Get nodes indexed by ID (backward compatible property).

        Returns TreeNode wrappers around facade's EntityNodes.
        """
        self._rebuild_cache()
        return self._nodes_cache

    @nodes_by_id.setter
    def nodes_by_id(self: Self, value: dict[str, TreeNode]) -> None:
        """Set nodes by ID (for backward compatibility during reset)."""
        self._nodes_cache = value
        self._cache_valid = True

    def get_or_create_facade(self: Self) -> ProfileFacade:
        """Get existing facade or create new one."""
        from metaseed.facade import ProfileFacade

        # Case-insensitive comparison since ProfileFacade lowercases profile names
        if self.facade is None or self.facade.profile.lower() != self.profile.lower():
            self.facade = ProfileFacade(self.profile, self.version)
            self._invalidate_cache()
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
                spec = facade._loader.load_profile(
                    version=facade.version, profile=self.profile
                )
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

        Delegates to facade.add_entity() and returns a TreeNode wrapper.
        Also updates any cached parent TreeNode's children list for
        backward compatibility with code that holds TreeNode references.

        Args:
            entity_type: Type of entity.
            instance: The entity instance.
            parent_id: Optional parent node ID for hierarchy.
            node_id: Optional node ID to preserve (for loading saved datasets).
        """
        facade = self.get_or_create_facade()

        # Convert instance to data dict for facade
        if hasattr(instance, "model_dump"):
            data = instance.model_dump(exclude_none=True)
        elif isinstance(instance, dict):
            data = instance
        else:
            data = {}

        # Add to facade
        entity_node = facade.add_entity(
            entity_type, data, node_id=node_id, parent_id=parent_id
        )

        # Create TreeNode wrapper for backward compatibility
        helper = getattr(facade, entity_type, None)
        if helper:
            label = helper.get_label(entity_node.instance)
        else:
            label = entity_node.label

        node = TreeNode(
            id=entity_node.id,
            entity_type=entity_node.entity_type,
            instance=entity_node.instance,
            label=label,
            parent_id=entity_node.parent_id,
        )

        # Update cached TreeNode structures for backward compatibility
        # This ensures code holding TreeNode references sees updates
        if parent_id and parent_id in self._nodes_cache:
            parent_tree_node = self._nodes_cache[parent_id]
            parent_tree_node.children.append(node)
        elif not parent_id:
            self._tree_cache.append(node)

        self._nodes_cache[node.id] = node

        return node

    def update_node(self: Self, node_id: str, instance: Any) -> TreeNode | None:
        """Update an existing node.

        Delegates to facade.update_entity() and returns updated TreeNode.
        """
        facade = self.get_or_create_facade()

        # Convert instance to data
        if hasattr(instance, "model_dump"):
            data = instance.model_dump(exclude_none=True)
        elif isinstance(instance, dict):
            data = instance
        else:
            return None

        entity_node = facade.update_entity(node_id, data)
        if not entity_node:
            return None

        self._invalidate_cache()

        # Return TreeNode wrapper
        helper = getattr(facade, entity_node.entity_type, None)
        if helper:
            label = helper.get_label(entity_node.instance)
        else:
            label = entity_node.label

        return TreeNode(
            id=entity_node.id,
            entity_type=entity_node.entity_type,
            instance=entity_node.instance,
            label=label,
            parent_id=entity_node.parent_id,
        )

    def delete_node(self: Self, node_id: str) -> bool:
        """Delete a node and all its children.

        Delegates to facade.delete_entity().
        """
        facade = self.get_or_create_facade()

        result = facade.delete_entity(node_id)
        if result:
            self._invalidate_cache()
            if self.editing_node_id == node_id:
                self.editing_node_id = None

        return result

    def get_tree_data(self: Self) -> list[dict]:
        """Get tree data for template rendering.

        Delegates to facade.get_tree().
        """
        facade = self.get_or_create_facade()
        return facade.get_tree()

    def reset(self: Self) -> None:
        """Reset all state."""
        if self.facade:
            self.facade.clear()
        self._tree_cache = []
        self._nodes_cache = {}
        self._cache_valid = True
        self.editing_node_id = None
        self.current_nested_items = {}
        self.nested_edit_stack = []
