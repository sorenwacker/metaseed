"""Interactive facade for creating profile entities.

This module provides a user-friendly API with tab completion and help
for creating MIAPPE, ISA, and other profile entities.

ProfileFacade serves as the single source of truth for:
- Entity schema helpers (EntityHelper instances)
- Entity instance storage (EntityNode instances)
- Relationship resolution via reference fields
- Tree/graph generation for visualization

This enables reuse across JupyterLab, CLI, MCP, and UI without
duplicating relationship logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Self
from uuid import uuid4

from pydantic import BaseModel

from metaseed.models import get_model
from metaseed.models.factory import create_model_from_spec, set_model_context
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import PRIMITIVE_TYPES, EntitySpec, FieldSpec, FieldType, ProfileSpec


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

    def to_dict(self) -> dict:
        """Convert node to dictionary for template rendering."""
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "label": self.label,
            "has_children": bool(self.children),
            "children": [c.to_dict() for c in self.children],
        }


class EntityHelper:
    """Helper class providing info and creation methods for an entity.

    Provides tab completion, field information, and guided entity creation.
    """

    def __init__(
        self: Self,
        entity_name: str,
        spec: EntitySpec,
        model: type[BaseModel],
        profile: str,
        version: str,
    ) -> None:
        """Initialize the entity helper.

        Args:
            entity_name: Name of the entity (e.g., "Investigation").
            spec: Entity specification from YAML.
            model: Generated Pydantic model class.
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.1").
        """
        self._name = entity_name
        self._spec = spec
        self._model = model
        self._profile = profile
        self._version = version

    @property
    def name(self: Self) -> str:
        """Entity name."""
        return self._name

    @property
    def description(self: Self) -> str:
        """Entity description from spec."""
        return self._spec.description

    @property
    def ontology_term(self: Self) -> str | None:
        """Ontology term for this entity."""
        return self._spec.ontology_term

    @property
    def required_fields(self: Self) -> list[str]:
        """List of required field names."""
        return [f.name for f in self._spec.fields if f.required]

    @property
    def optional_fields(self: Self) -> list[str]:
        """List of optional field names."""
        return [f.name for f in self._spec.fields if not f.required]

    @property
    def all_fields(self: Self) -> list[str]:
        """List of all field names."""
        return [f.name for f in self._spec.fields]

    @property
    def nested_fields(self: Self) -> dict[str, str]:
        """Fields that contain nested entities. Returns {field_name: entity_type}."""
        nested = {}
        for f in self._spec.fields:
            if f.type == FieldType.LIST and f.items:
                if f.items not in PRIMITIVE_TYPES:
                    nested[f.name] = f.items
            elif f.type == FieldType.ENTITY and f.items:
                nested[f.name] = f.items
        return nested

    @property
    def reference_fields(self: Self) -> dict[str, tuple[str, str]]:
        """Fields that reference other entities by ID.

        Returns {field_name: (target_entity, target_field)}.
        Example: {"sample_ref": ("Sample", "alias")}
        """
        refs = {}
        for f in self._spec.fields:
            if f.reference:
                # Parse "Entity.field" format
                parts = f.reference.split(".", 1)
                if len(parts) == 2:
                    refs[f.name] = (parts[0], parts[1])
        return refs

    @property
    def identifier_field(self: Self) -> str | None:
        """Field name used as display label for this entity.

        By convention, the first non-parent-ref, non-reference field in the entity
        definition is used as the identifier/label for display purposes.
        Reference fields (e.g., run_ref, sample_ref) should not be used as identifiers
        since they point to other entities rather than identifying this one.
        """
        for f in self._spec.fields:
            # Skip parent reference fields (these are auto-populated)
            if f.parent_ref:
                continue
            # Skip reference fields (these point to other entities)
            if f.reference:
                continue
            return f.name
        return None

    @property
    def example_data(self: Self) -> dict[str, Any]:
        """Example values for this entity from the spec.

        Returns:
            Dictionary of field names to example values.
            Empty dict if no example defined.
        """
        return self._spec.example or {}

    def field_info(self: Self, field_name: str) -> dict[str, Any]:
        """Get detailed information about a field.

        Args:
            field_name: Name of the field.

        Returns:
            Dictionary with field details.

        Raises:
            KeyError: If field not found.
        """
        for f in self._spec.fields:
            if f.name == field_name:
                info = {
                    "name": f.name,
                    "type": f.type.value,
                    "required": f.required,
                    "description": f.description,
                }
                if f.ontology_term:
                    info["ontology_term"] = f.ontology_term
                if f.items:
                    info["items"] = f.items
                if f.constraints:
                    info["constraints"] = {
                        k: v for k, v in f.constraints.model_dump().items() if v is not None
                    }
                return info
        raise KeyError(f"Field '{field_name}' not found in {self._name}")

    def get_label(self: Self, instance: BaseModel | dict[str, Any]) -> str:
        """Get a human-readable label for an entity instance.

        Looks for common identifier fields in order of preference:
        - title (for Investigation, Study)
        - name (for Person, Factor)
        - first_name + last_name (for Person)
        - unique_id / identifier
        - Falls back to first non-empty string field from spec

        Args:
            instance: Entity instance (Pydantic model or dict).

        Returns:
            Human-readable label string.
        """
        from metaseed.repositories.helpers import derive_label

        if hasattr(instance, "model_dump"):
            data = instance.model_dump()
        elif isinstance(instance, dict):
            data = instance
        else:
            return f"{self._name}"

        return derive_label(self._name, data, spec=self._spec)

    def help(self: Self) -> None:
        """Print detailed help for this entity."""
        print(f"\n{'=' * 60}")
        print(f"{self._name} ({self._profile} v{self._version})")
        print("=" * 60)

        if self._spec.description:
            print(f"\n{self._spec.description}")

        if self._spec.ontology_term:
            print(f"\nOntology: {self._spec.ontology_term}")

        print(f"\n--- Required Fields ({len(self.required_fields)}) ---")
        for f in self._spec.fields:
            if f.required:
                self._print_field(f)

        print(f"\n--- Optional Fields ({len(self.optional_fields)}) ---")
        for f in self._spec.fields:
            if not f.required:
                self._print_field(f)

        print()

    def _print_field(self: Self, f: FieldSpec) -> None:
        """Print a single field's information."""
        type_str = f.type.value
        if f.items:
            type_str = f"list[{f.items}]" if f.type == FieldType.LIST else f.items

        req = "*" if f.required else " "
        print(f"  {req} {f.name}: {type_str}")
        if f.description:
            # Wrap long descriptions
            desc = f.description[:70] + "..." if len(f.description) > 70 else f.description
            print(f"      {desc}")

    def example(self: Self) -> None:
        """Print example code for creating this entity."""
        print(f"\n# Create a {self._name}")
        print(f"{self._name} = profile.{self._name}")
        print()

        # Use spec example if available
        spec_example = self._spec.example or {}

        # Build example with required fields
        args = []
        for f in self._spec.fields:
            if f.required:
                # Use spec example value if available
                if f.name in spec_example:
                    val = spec_example[f.name]
                    if isinstance(val, str):
                        args.append(f'{f.name}="{val}"')
                    else:
                        args.append(f"{f.name}={val}")
                elif f.type == FieldType.STRING:
                    args.append(f'{f.name}="..."')
                elif f.type == FieldType.INTEGER:
                    args.append(f"{f.name}=0")
                elif f.type == FieldType.FLOAT:
                    args.append(f"{f.name}=0.0")
                elif f.type == FieldType.BOOLEAN:
                    args.append(f"{f.name}=True")
                elif f.type == FieldType.DATE:
                    args.append(f"{f.name}=datetime.date.today()")
                elif f.type == FieldType.LIST:
                    args.append(f"{f.name}=[]")
                else:
                    args.append(f'{f.name}="..."')

        args_str = ",\n    ".join(args)
        print(f"instance = {self._name}.create(")
        print(f"    {args_str}")
        print(")")

    def create(self: Self, **kwargs: Any) -> BaseModel:
        """Create an instance of this entity.

        Args:
            **kwargs: Field values for the entity.

        Returns:
            New entity instance.

        Note:
            Pydantic may modify nested dict values in-place during validation.
            If you need to reuse the input data, make a deep copy first:
            ``import copy; data = copy.deepcopy(original_data)``

        Example:
            >>> inv = profile.Investigation.create(
            ...     unique_id="INV-001",
            ...     title="My Investigation",
            ... )
        """
        return self._model(**kwargs)

    def __call__(self: Self, **kwargs: Any) -> BaseModel:
        """Create an instance (shorthand for create()).

        Example:
            >>> inv = profile.Investigation(unique_id="INV-001", title="My Investigation")
        """
        return self.create(**kwargs)

    def __repr__(self: Self) -> str:
        return f"<{self._name}: {len(self.required_fields)} required, {len(self.optional_fields)} optional fields>"


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
        self._loader = loader if loader is not None else SpecLoader(profile=self._profile)

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
        self._instances: dict[str, EntityNode] = {}  # Entity instance storage
        self._index: dict[str, str] = {}  # alias/unique_id -> node_id lookup
        self._load_entities()

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
            )

    # ========================================================================
    # Instance Storage Methods
    # ========================================================================

    def add_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        node_id: str | None = None,
        parent_id: str | None = None,
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
        helper = getattr(self, entity_type)
        instance = helper.create(**data)

        # Resolve parent: explicit parent_id takes precedence, then reference fields
        resolved_parent_id = parent_id
        if resolved_parent_id is None:
            resolved_parent_id = self._resolve_parent(entity_type, data)

        node = EntityNode(
            id=node_id or uuid4().hex[:8],
            entity_type=entity_type,
            instance=instance,
            parent_id=resolved_parent_id,
        )

        self._instances[node.id] = node

        # Link to parent's children list if parent exists
        if resolved_parent_id and resolved_parent_id in self._instances:
            parent_node = self._instances[resolved_parent_id]
            parent_node.children.append(node)

        # Index by common identifier fields for reference lookups
        for id_field in ["alias", "unique_id", "identifier"]:
            id_value = data.get(id_field)
            if id_value:
                self._index[str(id_value)] = node.id

        return node

    def _resolve_parent(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
    ) -> str | None:
        """Find parent node via reference fields.

        Examines the entity's reference fields (e.g., study_ref, sample_ref)
        and looks up the referenced entity in the index.

        Args:
            entity_type: Type of entity being created.
            data: Entity data containing potential reference field values.

        Returns:
            Parent node ID if found, None otherwise.
        """
        helper = self._entities.get(entity_type)
        if not helper:
            return None

        for field_name in helper.reference_fields:
            ref_value = data.get(field_name)
            if ref_value and str(ref_value) in self._index:
                return self._index[str(ref_value)]

        return None

    def get_entity(self: Self, node_id: str) -> EntityNode | None:
        """Get an entity node by its ID.

        Args:
            node_id: The node ID to look up.

        Returns:
            EntityNode if found, None otherwise.
        """
        return self._instances.get(node_id)

    def get_entity_by_ref(self: Self, ref_value: str) -> EntityNode | None:
        """Get an entity node by its reference value (alias/unique_id).

        Args:
            ref_value: The alias or unique_id to look up.

        Returns:
            EntityNode if found, None otherwise.
        """
        node_id = self._index.get(ref_value)
        if node_id:
            return self._instances.get(node_id)
        return None

    def update_entity(
        self: Self,
        node_id: str,
        data: dict[str, Any],
    ) -> EntityNode | None:
        """Update an existing entity's data.

        Args:
            node_id: ID of the node to update.
            data: New field values.

        Returns:
            Updated EntityNode if found, None otherwise.
        """
        node = self._instances.get(node_id)
        if not node:
            return None

        helper = getattr(self, node.entity_type)

        # Remove old index entries
        old_data = node.instance.model_dump() if hasattr(node.instance, "model_dump") else {}
        for id_field in ["alias", "unique_id", "identifier"]:
            old_value = old_data.get(id_field)
            if old_value and str(old_value) in self._index:
                if self._index[str(old_value)] == node_id:
                    del self._index[str(old_value)]

        # Create new instance
        node.instance = helper.create(**data)

        # Add new index entries
        for id_field in ["alias", "unique_id", "identifier"]:
            new_value = data.get(id_field)
            if new_value:
                self._index[str(new_value)] = node_id

        return node

    def delete_entity(self: Self, node_id: str) -> bool:
        """Delete an entity and all its children recursively.

        Args:
            node_id: ID of the node to delete.

        Returns:
            True if deleted, False if not found.
        """
        node = self._instances.get(node_id)
        if not node:
            return False

        def remove_recursively(n: EntityNode) -> None:
            for child in n.children:
                remove_recursively(child)
            # Remove from index
            if n.instance and hasattr(n.instance, "model_dump"):
                data = n.instance.model_dump()
                for id_field in ["alias", "unique_id", "identifier"]:
                    id_value = data.get(id_field)
                    if id_value and str(id_value) in self._index:
                        del self._index[str(id_value)]
            self._instances.pop(n.id, None)

        # Remove from parent's children list
        if node.parent_id and node.parent_id in self._instances:
            parent = self._instances[node.parent_id]
            parent.children = [c for c in parent.children if c.id != node_id]

        remove_recursively(node)
        return True

    def get_children(self: Self, node_id: str) -> list[EntityNode]:
        """Get all direct children of a node.

        Args:
            node_id: ID of the parent node.

        Returns:
            List of child EntityNodes.
        """
        node = self._instances.get(node_id)
        if node:
            return node.children
        return []

    def get_roots(self: Self) -> list[EntityNode]:
        """Get all root nodes (nodes without parents).

        Returns:
            List of root EntityNodes.
        """
        return [n for n in self._instances.values() if n.parent_id is None]

    def get_tree(self: Self) -> list[dict]:
        """Get hierarchical tree for visualization.

        Returns tree structure starting from root nodes, with each node
        containing its children recursively.

        Returns:
            List of dicts representing the tree structure:
            [{"id": "...", "entity_type": "...", "label": "...", "children": [...]}]
        """
        roots = self.get_roots()

        def node_to_dict(node: EntityNode) -> dict:
            # Get label using helper's get_label for consistency
            helper = self._entities.get(node.entity_type)
            if helper and node.instance:
                label = helper.get_label(node.instance)
            else:
                label = node.label

            return {
                "id": node.id,
                "entity_type": node.entity_type,
                "label": label,
                "has_children": bool(node.children),
                "children": [node_to_dict(c) for c in node.children],
            }

        return [node_to_dict(r) for r in roots]

    def to_graph(self: Self) -> dict:
        """Export entity graph in vis.js format.

        Builds nodes and edges for visualization. Includes:
        - Containment edges (parent-child, solid lines)
        - Reference edges (entity references, dashed lines)

        Returns:
            Dictionary with 'nodes' and 'edges' lists for vis.js.
        """
        nodes: list[dict] = []
        edges: list[dict] = []

        # Maps for resolving references by unique_id/alias
        unique_id_to_vis_id: dict[str, str] = {}

        def truncate(text: str, max_len: int = 25) -> str:
            if len(text) <= max_len:
                return text
            return text[: max_len - 1] + "..."

        def format_value(value: Any, max_len: int = 50) -> str:
            if value is None:
                return ""
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, date | datetime):
                return str(value)
            if isinstance(value, list):
                if not value:
                    return ""
                if len(value) <= 3:
                    return ", ".join(str(v) for v in value)
                return f"{len(value)} items"
            if isinstance(value, dict):
                return "[object]"
            text = str(value)
            if len(text) > max_len:
                return text[: max_len - 3] + "..."
            return text

        def build_tooltip(entity_type: str, label: str, data: dict) -> str:
            lines = [f"{entity_type}: {label}"]
            shown = 0
            for key, value in data.items():
                if shown >= 8:
                    lines.append("...")
                    break
                formatted = format_value(value)
                if (formatted and not isinstance(value, list)) or (
                    isinstance(value, list) and value
                ):
                    lines.append(f"{key}: {formatted}")
                    shown += 1
            return "\n".join(lines)

        def process_node(node: EntityNode, parent_vis_id: str | None, level: int) -> None:
            vis_id = node.id

            # Get entity data
            entity_data = {}
            if node.instance and hasattr(node.instance, "model_dump"):
                entity_data = node.instance.model_dump(exclude_none=True)

            # Map identifier to vis_id for reference resolution
            helper = self._entities.get(node.entity_type)
            if helper and helper.identifier_field:
                id_value = entity_data.get(helper.identifier_field)
                if id_value:
                    unique_id_to_vis_id[str(id_value)] = vis_id

            # Get label
            if helper:
                label = helper.get_label(node.instance)
            else:
                label = node.label

            tooltip = build_tooltip(node.entity_type, label, entity_data)

            nodes.append(
                {
                    "id": vis_id,
                    "label": truncate(label, 25),
                    "title": tooltip,
                    "group": node.entity_type,
                    "level": level,
                }
            )

            # Parent-child containment edge
            if parent_vis_id:
                edges.append(
                    {
                        "id": f"{parent_vis_id}->{vis_id}",
                        "from": parent_vis_id,
                        "to": vis_id,
                    }
                )

            # Process children
            for child in node.children:
                process_node(child, vis_id, level + 1)

        # First pass: build all nodes
        for root in self.get_roots():
            process_node(root, None, 0)

        # Second pass: add reference edges
        for node in self._instances.values():
            if not node.instance or not hasattr(node.instance, "model_dump"):
                continue

            vis_id = node.id
            entity_data = node.instance.model_dump(exclude_none=True)
            helper = self._entities.get(node.entity_type)
            if not helper:
                continue

            # Check reference fields (e.g., sample_ref -> Sample.alias)
            for field_name in helper.reference_fields:
                ref_value = entity_data.get(field_name)
                if not ref_value or not isinstance(ref_value, str):
                    continue

                target_vis_id = unique_id_to_vis_id.get(ref_value)
                if target_vis_id and target_vis_id != vis_id:
                    edges.append(
                        {
                            "id": f"{vis_id}->{target_vis_id}:{field_name}",
                            "from": vis_id,
                            "to": target_vis_id,
                            "dashes": True,
                            "label": field_name,
                            "font": {"size": 8},
                        }
                    )

            # Check nested fields for list references
            for field_name in helper.nested_fields:
                ref_value = entity_data.get(field_name)
                if not ref_value:
                    continue

                ref_ids = []
                if isinstance(ref_value, list):
                    for item in ref_value:
                        if isinstance(item, str):
                            ref_ids.append(item)
                        elif isinstance(item, dict):
                            from metaseed.repositories.helpers import get_identifier

                            item_id = get_identifier(item)
                            if item_id:
                                ref_ids.append(item_id)

                for ref_id in ref_ids:
                    target_vis_id = unique_id_to_vis_id.get(ref_id)
                    if target_vis_id and target_vis_id != vis_id:
                        edges.append(
                            {
                                "id": f"{vis_id}->{target_vis_id}:{field_name}",
                                "from": vis_id,
                                "to": target_vis_id,
                                "dashes": True,
                                "label": field_name,
                                "font": {"size": 8},
                            }
                        )

        return {"nodes": nodes, "edges": edges}

    def to_dict(self: Self) -> list[dict]:
        """Export all entities for serialization.

        Returns a flat list of entity data with metadata for reconstruction.
        Uses _parent_unique_id for parent references (stable across reloads).

        Returns:
            List of entity dictionaries with _type and optional _parent_unique_id.
        """
        entities: list[dict] = []

        def serialize_node(node: EntityNode, parent_unique_id: str | None = None) -> None:
            if node.instance and hasattr(node.instance, "model_dump"):
                data = node.instance.model_dump(exclude_none=True)
            else:
                data = {}

            data["_type"] = node.entity_type
            if parent_unique_id:
                data["_parent_unique_id"] = parent_unique_id

            entities.append(data)

            # Get this node's unique_id for children to reference
            node_unique_id = data.get("unique_id") or data.get("alias")

            for child in node.children:
                serialize_node(child, node_unique_id)

        for root in self.get_roots():
            serialize_node(root)

        return entities

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
        self.clear()

        id_to_node: dict[str, EntityNode] = {}  # unique_id/alias -> node
        old_id_to_node: dict[str, EntityNode] = {}  # old _node_id -> node
        nodes_with_parent: list[tuple[EntityNode, str, bool]] = []

        for entity_data in entities:
            entity_type = entity_data.get("_type")
            if not entity_type:
                continue

            try:
                helper = self._entities.get(entity_type)
                if not helper:
                    continue

                parent_unique_id = entity_data.get("_parent_unique_id")
                old_parent_id = entity_data.get("_parent_id")
                old_node_id = entity_data.get("_node_id")

                # Filter to valid fields only (lenient loading)
                valid_fields = set(helper.all_fields)
                fields = {
                    k: v
                    for k, v in entity_data.items()
                    if not k.startswith("_") and k in valid_fields
                }

                # Create node without auto-linking (we'll link in passes below)
                instance = helper.create(**fields)
                node = EntityNode(
                    id=old_node_id or uuid4().hex[:8],
                    entity_type=entity_type,
                    instance=instance,
                    parent_id=None,
                )
                self._instances[node.id] = node

                # Index by identifier fields
                entity_id = fields.get("unique_id") or fields.get("alias")
                if entity_id:
                    id_to_node[str(entity_id)] = node
                    self._index[str(entity_id)] = node.id

                if old_node_id:
                    old_id_to_node[old_node_id] = node

                if parent_unique_id:
                    nodes_with_parent.append((node, parent_unique_id, True))
                elif old_parent_id:
                    nodes_with_parent.append((node, old_parent_id, False))

            except Exception:  # noqa: S112
                continue

        # Link nodes to parents by stored references
        for node, parent_ref, is_unique_id in nodes_with_parent:
            if is_unique_id:
                parent_node = id_to_node.get(parent_ref)
            else:
                parent_node = old_id_to_node.get(parent_ref)

            if parent_node:
                node.parent_id = parent_node.id
                parent_node.children.append(node)

        # Link children via parent's nested arrays
        for node in list(self._instances.values()):
            if node.parent_id:
                continue

            helper = self._entities.get(node.entity_type)
            if not helper:
                continue

            node_data = node.instance.model_dump() if node.instance else {}

            for field_name in helper.nested_fields:
                child_ids = node_data.get(field_name, [])
                if not isinstance(child_ids, list):
                    continue

                for child_id in child_ids:
                    child_node = id_to_node.get(str(child_id))
                    if child_node and child_node.parent_id is None:
                        child_node.parent_id = node.id
                        node.children.append(child_node)

        # Link via reference fields
        for node in list(self._instances.values()):
            if node.parent_id:
                continue

            helper = self._entities.get(node.entity_type)
            if not helper:
                continue

            node_data = node.instance.model_dump() if node.instance else {}

            for field_name in helper.reference_fields:
                ref_value = node_data.get(field_name)
                if not ref_value:
                    continue

                parent_node = id_to_node.get(str(ref_value))
                if parent_node and parent_node.id != node.id:
                    node.parent_id = parent_node.id
                    parent_node.children.append(node)
                    break

        return len(self._instances)

    def clear(self: Self) -> None:
        """Clear all stored entity instances."""
        self._instances.clear()
        self._index.clear()

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

        print(f"\n{'=' * 60}")
        print(f"{self._profile.upper()} Profile v{self._version}")
        print("=" * 60)

        print(f"\nEntities ({len(self._entities)}):")
        for name in sorted(self._entities.keys()):
            helper = self._entities[name]
            req = len(helper.required_fields)
            opt = len(helper.optional_fields)
            print(f"  {name}: {req} required, {opt} optional fields")

        print("\nUsage:")
        print("  profile.Investigation.help()    # Show Investigation fields")
        print("  profile.Investigation.example() # Show example code")
        print("  inv = profile.Investigation(    # Create an instance")
        print("      unique_id='...', title='...'")
        print("  )")
        print()

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


# Convenience instances for common profiles
def miappe(version: str = "1.1") -> ProfileFacade:
    """Get MIAPPE profile facade.

    Args:
        version: MIAPPE version (default: "1.1").

    Returns:
        ProfileFacade for MIAPPE.

    Example:
        >>> from metaseed.facade import miappe
        >>> m = miappe()
        >>> m.Investigation.help()
    """
    return ProfileFacade("miappe", version)


def isa(version: str = "1.0") -> ProfileFacade:
    """Get ISA profile facade.

    Args:
        version: ISA version (default: "1.0").

    Returns:
        ProfileFacade for ISA.

    Example:
        >>> from metaseed.facade import isa
        >>> i = isa()
        >>> i.Investigation.help()
    """
    return ProfileFacade("isa", version)
