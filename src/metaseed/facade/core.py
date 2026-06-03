"""Core ProfileFacade class for interactive metadata creation.

This module provides the main ProfileFacade class that serves as the
entry point for creating and managing profile entities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from metaseed.facade.graph import get_tree, to_graph
from metaseed.facade.helper import EntityHelper
from metaseed.facade.node import EntityNode
from metaseed.facade.store import EntityStore
from metaseed.models import get_model
from metaseed.models.factory import create_model_from_spec, set_model_context
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import ProfileSpec

__all__ = ["ProfileFacade"]


class ProfileFacade:
    """Interactive facade for a profile (MIAPPE, ISA, etc.).

    Provides tab completion and help for all entities in the profile.

    Supports dependency injection for custom loading strategies:
    - Provide a custom `loader` to use alternative spec loading
    - Provide a pre-loaded `spec` to bypass the loader entirely

    Example:
        >>> from metaseed.facade import ProfileFacade
        >>> miappe = ProfileFacade("miappe", "1.1")
        >>> miappe.entities  # List all entities
        >>> miappe.Investigation.help()  # Show help for Investigation
        >>> inv = miappe.Investigation(unique_id="INV-001", title="My Investigation")

        # With custom loader:
        >>> custom_loader = MySpecLoader(profile="miappe")
        >>> facade = ProfileFacade("miappe", loader=custom_loader)

        # With pre-loaded spec (bypasses loader):
        >>> spec = ProfileSpec(...)
        >>> facade = ProfileFacade("miappe", spec=spec)
    """

    def __init__(
        self: Self,
        profile: str = "miappe",
        version: str | None = None,
        *,
        loader: SpecLoader | None = None,
        spec: ProfileSpec | None = None,
    ) -> None:
        """Initialize the profile facade.

        Args:
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version. If None, uses the latest available
                (or spec.version if spec is provided).
            loader: Optional custom SpecLoader instance. If not provided,
                a default loader is created. When a custom loader is provided,
                it is used for all spec loading operations.
            spec: Optional pre-loaded ProfileSpec. If provided, the loader
                is not used for entity loading. The spec.version takes
                precedence over the version parameter.
        """
        self._profile = profile.lower()
        self._spec = spec
        self._custom_loader = loader is not None

        # Use provided loader or create default
        self._loader = (
            loader if loader is not None else SpecLoader(profile=self._profile)
        )

        # Determine version
        if spec is not None:
            self._version = spec.version
        elif version is not None:
            self._version = version
        else:
            versions = self._loader.list_versions()
            if not versions:
                raise ValueError(f"No versions found for profile: {profile}")
            self._version = versions[-1]

        self._entities: dict[str, EntityHelper] = {}
        self._load_entities()

        # Initialize EntityStore with helper getter and instance creator
        self._store = EntityStore(
            helper_getter=self._get_helper,
            instance_creator=self._create_instance,
        )

    def _get_helper(self: Self, entity_type: str) -> EntityHelper:
        """Get EntityHelper by entity type name.

        Args:
            entity_type: Name of the entity type.

        Returns:
            EntityHelper for the entity type.

        Raises:
            KeyError: If entity type not found.
        """
        if entity_type in self._entities:
            return self._entities[entity_type]
        raise KeyError(f"Entity type '{entity_type}' not found")

    def _create_instance(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        skip_validation: bool = False,
    ) -> BaseModel:
        """Create a model instance.

        Args:
            entity_type: Name of the entity type.
            data: Field values for the entity.
            skip_validation: If True, skip Pydantic validation.

        Returns:
            Pydantic model instance.
        """
        helper = getattr(self, entity_type)
        return helper.create(skip_validation=skip_validation, **data)

    def _store_entity(self: Self, entity_type: str, data: dict[str, Any]) -> EntityNode:
        """Store an entity (callback for EntityHelper).

        Args:
            entity_type: Name of the entity type.
            data: Field values for the entity.

        Returns:
            EntityNode for the stored entity.
        """
        return self._store.add_entity(entity_type, data)

    def _load_entities(self: Self) -> None:
        """Load all entity helpers for this profile.

        Uses the injected spec if available, otherwise falls back to the loader.
        When a spec or custom loader is injected, models are created directly
        from entity specs to avoid requiring the spec to exist on the filesystem.
        """
        if self._spec is not None:
            entity_names = self._spec.list_entities()
        else:
            entity_names = self._loader.list_entities(self._version)

        # Set model context for nested entity resolution
        set_model_context(self._profile, self._version)

        # Use direct model creation when custom loader or spec is provided.
        # This avoids get_model creating its own internal loader.
        use_direct_model_creation = self._spec is not None or self._custom_loader

        for name in entity_names:
            if self._spec is not None:
                entity_spec = self._spec.get_entity(name)
            else:
                entity_spec = self._loader.load_entity(name, self._version)

            if use_direct_model_creation:
                # Create model directly from spec to avoid filesystem lookup
                model = create_model_from_spec(entity_spec)
            else:
                model = get_model(name, self._version, self._profile)

            self._entities[name] = EntityHelper(
                entity_name=name,
                spec=entity_spec,
                model=model,
                profile=self._profile,
                version=self._version,
                store_callback=self._store_entity,
            )

    # ========================================================================
    # Instance Storage Methods (delegated to EntityStore)
    # ========================================================================

    def add_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        node_id: str | None = None,
        parent_id: str | None = None,
        skip_validation: bool = False,
    ) -> EntityNode:
        """Add an entity instance and auto-link to parent via reference fields.

        This method creates an EntityNode, validates the data against the schema,
        and automatically establishes parent-child relationships by examining
        reference fields in the entity data.

        Args:
            entity_type: Type of entity (e.g., "Study", "Sample").
            data: Field values for the entity.
            node_id: Optional node ID. If not provided, generates a UUID.
            parent_id: Optional explicit parent node ID. If not provided,
                      attempts to resolve parent via reference fields.
            skip_validation: If True, skip Pydantic validation. Use for
                progressive editing where entities are saved with incomplete data.

        Returns:
            The created EntityNode.

        Raises:
            AttributeError: If entity_type is not found in this profile.

        Example:
            >>> facade = ProfileFacade("ena", "1.0")
            >>> facade.add_entity("Study", {"alias": "s1", "title": "My Study"})
            >>> facade.add_entity("Sample", {"alias": "sam1", "study_ref": "s1", ...})
            >>> # Sample is auto-linked to Study via study_ref
        """
        return self._store.add_entity(
            entity_type, data, node_id, parent_id, skip_validation
        )

    def get_entity(self: Self, node_id: str) -> EntityNode | None:
        """Get an entity node by its ID.

        Args:
            node_id: The node ID to look up.

        Returns:
            EntityNode if found, None otherwise.
        """
        return self._store.get_entity(node_id)

    def get_entity_by_ref(self: Self, ref_value: str) -> EntityNode | None:
        """Get an entity node by its reference value (alias/unique_id).

        Args:
            ref_value: The alias or unique_id to look up.

        Returns:
            EntityNode if found, None otherwise.
        """
        return self._store.get_entity_by_ref(ref_value)

    def update_entity(
        self: Self,
        node_id: str,
        data: dict[str, Any],
        skip_validation: bool = False,
    ) -> EntityNode | None:
        """Update an existing entity's data.

        Args:
            node_id: ID of the node to update.
            data: New field values.
            skip_validation: If True, skip Pydantic validation.

        Returns:
            Updated EntityNode if found, None otherwise.
        """
        return self._store.update_entity(node_id, data, skip_validation)

    def delete_entity(self: Self, node_id: str) -> bool:
        """Delete an entity and all its children recursively.

        Args:
            node_id: ID of the node to delete.

        Returns:
            True if deleted, False if not found.
        """
        return self._store.delete_entity(node_id)

    def get_children(self: Self, node_id: str) -> list[EntityNode]:
        """Get all direct children of a node.

        Args:
            node_id: ID of the parent node.

        Returns:
            List of child EntityNodes.
        """
        return self._store.get_children(node_id)

    def get_roots(self: Self) -> list[EntityNode]:
        """Get all root nodes (nodes without parents).

        Returns:
            List of root EntityNodes.
        """
        return self._store.get_roots()

    def list_entities(self: Self, entity_type: str | None = None) -> list[EntityNode]:
        """List all stored entities, optionally filtered by type.

        Args:
            entity_type: Optional entity type to filter by (e.g., "Investigation").

        Returns:
            List of EntityNodes matching the filter.

        Example:
            >>> m.list_entities()  # All entities
            >>> m.list_entities("Investigation")  # Only Investigations
        """
        all_nodes = list(self._store._instances.values())
        if entity_type:
            return [n for n in all_nodes if n.entity_type == entity_type]
        return all_nodes

    def to_dict(self: Self) -> list[dict]:
        """Export all entities for serialization.

        Returns a flat list of entity data with metadata for reconstruction.
        Uses _parent_unique_id for parent references (stable across reloads).

        Returns:
            List of entity dictionaries with _type and optional _parent_unique_id.
        """
        return self._store.to_dict()

    def load_from_dict(self: Self, entities: list[dict]) -> int:
        """Load entities from serialized data.

        Reconstructs the entity graph from a flat list of entity dictionaries.
        Handles parent relationships via _parent_id, _parent_unique_id, and
        reference fields.

        Args:
            entities: List of entity dictionaries with _type metadata.

        Returns:
            Number of entities loaded.
        """
        return self._store.load_from_dict(entities)

    def load_yaml(self: Self, path: str | Path) -> int:
        """Load entities from a YAML dataset file.

        Args:
            path: Path to the YAML file containing entity data.

        Returns:
            Number of entities loaded.

        Example:
            >>> facade = ProfileFacade("miappe", "1.2")
            >>> facade.load_yaml("my-dataset.yaml")
        """
        import yaml

        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)

        # Support both flat list and wrapped format
        if isinstance(data, list):
            entities = data
        elif isinstance(data, dict) and "entities" in data:
            entities = data["entities"]
        else:
            # Assume it's a single root entity (like Investigation with nested studies)
            entities = [data]

        return self.load_from_dict(entities)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProfileFacade:
        """Create a ProfileFacade from a custom spec YAML file.

        Args:
            path: Path to the profile spec YAML file.

        Returns:
            ProfileFacade configured with the custom spec.

        Example:
            >>> facade = ProfileFacade.from_yaml("my-custom-spec.yaml")
            >>> facade.MyEntity.help()
        """
        import yaml

        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)

        spec = ProfileSpec(**data)
        return cls(spec.name, spec=spec)

    def clear(self: Self) -> None:
        """Clear all stored entity instances."""
        self._store.clear()

    # ========================================================================
    # Tree and Graph Methods
    # ========================================================================

    def get_tree(self: Self) -> list[dict]:
        """Get hierarchical tree for visualization.

        Returns tree structure starting from root nodes, with each node
        containing its children recursively.

        Returns:
            List of dicts representing the tree structure:
            [{"id": "...", "entity_type": "...", "label": "...", "children": [...]}]
        """
        return get_tree(self._store, self._entities)

    def to_graph(self: Self) -> dict:
        """Export entity graph in vis.js format.

        Builds nodes and edges for visualization. Includes:
        - Containment edges (parent-child, solid lines)
        - Reference edges (entity references, dashed lines)

        Returns:
            Dictionary with 'nodes' and 'edges' lists for vis.js.
        """
        return to_graph(self._store, self._entities)

    # ========================================================================
    # Properties
    # ========================================================================

    @property
    def profile(self: Self) -> str:
        """Profile name."""
        return self._profile

    @property
    def version(self: Self) -> str:
        """Profile version."""
        return self._version

    @property
    def entities(self: Self) -> list[str]:
        """List of available entity names in hierarchical order."""
        return list(self._entities.keys())

    @property
    def _instances(self: Self) -> dict[str, EntityNode]:
        """Direct access to entity instances (for backward compatibility).

        Prefer using get_entity(), get_roots(), etc. for new code.
        """
        return self._store._instances

    @property
    def _index(self: Self) -> dict[str, str]:
        """Direct access to identifier index (for backward compatibility).

        Prefer using get_entity_by_ref() for new code.
        """
        return self._store._index

    def get_helper(self: Self, entity_type: str) -> EntityHelper | None:
        """Get an EntityHelper by entity type name.

        Public method to access entity helpers without accessing internal state.

        Args:
            entity_type: Name of the entity type.

        Returns:
            EntityHelper if found, None otherwise.
        """
        return self._entities.get(entity_type)

    def __getattr__(self: Self, name: str) -> EntityHelper:
        """Get an entity helper by name (enables tab completion).

        Args:
            name: Entity name (e.g., "Investigation", "Study").

        Returns:
            EntityHelper for the entity.

        Raises:
            AttributeError: If entity not found.
        """
        if name.startswith("_"):
            raise AttributeError(name)

        # Try exact match
        if name in self._entities:
            return self._entities[name]

        # Try case-insensitive match
        for entity_name, helper in self._entities.items():
            if entity_name.lower() == name.lower():
                return helper

        raise AttributeError(
            f"Entity '{name}' not found in {self._profile} v{self._version}. "
            f"Available: {', '.join(self.entities)}"
        )

    def __dir__(self: Self) -> list[str]:
        """Enable tab completion for entities."""
        return list(self._entities.keys()) + [
            "profile",
            "version",
            "entities",
            "help",
            "search",
        ]

    def help(self: Self, entity_name: str | None = None) -> None:
        """Print help for the profile or a specific entity.

        Args:
            entity_name: If provided, show help for that entity.
                        If None, show profile overview.
        """
        if entity_name:
            helper = getattr(self, entity_name)
            helper.help()
            return

        print(f"\n{'=' * 60}")  # noqa: T201
        print(f"{self._profile.upper()} Profile v{self._version}")  # noqa: T201
        print("=" * 60)  # noqa: T201

        print(f"\nEntities ({len(self._entities)}):")  # noqa: T201
        for name in sorted(self._entities.keys()):
            helper = self._entities[name]
            req = len(helper.required_fields)
            opt = len(helper.optional_fields)
            print(f"  {name}: {req} required, {opt} optional fields")  # noqa: T201

        print("\nUsage:")  # noqa: T201
        print("  profile.Investigation.help()    # Show Investigation fields")  # noqa: T201
        print("  profile.Investigation.example() # Show example code")  # noqa: T201
        print("  inv = profile.Investigation(    # Create an instance")  # noqa: T201
        print("      unique_id='...', title='...'")  # noqa: T201
        print("  )")  # noqa: T201
        print()  # noqa: T201

    def search(self: Self, query: str) -> list[str]:
        """Search for entities or fields containing the query string.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List of matching entity or field names.
        """
        query = query.lower()
        results = []

        for name, helper in self._entities.items():
            # Check entity name
            if query in name.lower():
                results.append(f"{name} (entity)")

            # Check field names
            for field_name in helper.all_fields:
                if query in field_name.lower():
                    results.append(f"{name}.{field_name}")

        return sorted(set(results))

    def __repr__(self: Self) -> str:
        return f"<ProfileFacade: {self._profile} v{self._version} ({len(self._entities)} entities)>"
