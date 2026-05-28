"""Public API client for metaseed.

This module provides MetaseedClient, a clean entry point for working with
metadata schemas and entities. It wraps ProfileFacade and provides a
stable public interface.

Example:
    >>> from metaseed import MetaseedClient
    >>> client = MetaseedClient("miappe", "1.2")
    >>> client.list_entity_types()
    ['Investigation', 'Study', 'Person', ...]
    >>> inv = client.create_entity("Investigation", {"unique_id": "INV-001", "title": "My Study"})
    >>> client.validate()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from metaseed.api.entities import Entity, EntityNode
from metaseed.api.errors import (
    EntityNotFoundError,
    EntityTypeNotFoundError,
    ProfileNotFoundError,
)
from metaseed.api.schema import EntitySchema, FieldInfo, ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from metaseed.facade import EntityNode as InternalEntityNode
    from metaseed.specs.schema import ProfileSpec


class MetaseedClient:
    """Clean public API for metaseed metadata management.

    MetaseedClient provides a single entry point for working with metadata
    schemas, creating entities, and validating data. It wraps the internal
    ProfileFacade to provide a stable, documented public interface.

    This is the recommended way to use metaseed programmatically. For
    interactive use in Jupyter notebooks, the ProfileFacade convenience
    functions (miappe(), isa(), etc.) may be more convenient.

    Example:
        >>> from metaseed import MetaseedClient
        >>>
        >>> # Create client for MIAPPE profile
        >>> client = MetaseedClient("miappe", "1.2")
        >>>
        >>> # Create entities
        >>> inv = client.create_entity("Investigation", {
        ...     "unique_id": "INV-001",
        ...     "title": "Drought Tolerance Study"
        ... })
        >>>
        >>> # Add child entity
        >>> study = client.create_entity("Study", {
        ...     "unique_id": "STU-001",
        ...     "title": "Field Trial 2024"
        ... }, parent_id=inv.id)
        >>>
        >>> # Validate all entities
        >>> result = client.validate()
        >>> if not result.valid:
        ...     for issue in result.issues:
        ...         print(f"{issue.field}: {issue.message}")

    Attributes:
        profile: Name of the loaded profile.
        version: Version of the loaded profile.
    """

    def __init__(self, profile: str, version: str | None = None) -> None:
        """Initialize the client with a profile.

        Args:
            profile: Profile name (e.g., "miappe", "isa", "ena").
            version: Profile version. If None, uses the latest available.

        Raises:
            ProfileNotFoundError: If profile or version not found.
        """
        from metaseed.facade import ProfileFacade
        from metaseed.specs.loader import SpecLoadError

        try:
            self._facade = ProfileFacade(profile, version)
        except (SpecLoadError, ValueError) as e:
            raise ProfileNotFoundError(profile, version) from e

    @classmethod
    def from_spec(cls, spec: dict[str, Any] | ProfileSpec) -> MetaseedClient:
        """Create client from a custom spec dictionary.

        Use this method when working with custom or dynamically-generated
        schemas that are not installed as profile files.

        Args:
            spec: Profile specification as a dict or ProfileSpec object.

        Returns:
            MetaseedClient configured with the custom spec.

        Example:
            >>> spec = {
            ...     "version": "1.0",
            ...     "name": "custom",
            ...     "entities": {
            ...         "Sample": {
            ...             "fields": [{"name": "id", "type": "string", "required": True}]
            ...         }
            ...     }
            ... }
            >>> client = MetaseedClient.from_spec(spec)
        """
        from metaseed.facade import ProfileFacade
        from metaseed.specs.schema import ProfileSpec

        if isinstance(spec, dict):
            spec = ProfileSpec(**spec)

        instance = cls.__new__(cls)
        instance._facade = ProfileFacade(spec.name, spec=spec)
        return instance

    @classmethod
    def from_yaml(cls, path: str) -> MetaseedClient:
        """Create client from a custom spec YAML file.

        Args:
            path: Path to the profile spec YAML file.

        Returns:
            MetaseedClient configured with the custom spec.

        Example:
            >>> client = MetaseedClient.from_yaml("my-custom-spec.yaml")
        """
        from metaseed.facade import ProfileFacade

        instance = cls.__new__(cls)
        instance._facade = ProfileFacade.from_yaml(path)
        return instance

    # ========================================================================
    # Entity CRUD Operations
    # ========================================================================

    def create_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str | None = None,
        skip_validation: bool = False,
    ) -> Entity:
        """Create a new entity instance.

        Creates an entity of the specified type with the provided data.
        By default, the entity is validated against the schema during creation.

        Args:
            entity_type: Type of entity to create (e.g., "Investigation").
            data: Field values for the entity.
            parent_id: Optional parent entity ID for hierarchical linking.
            skip_validation: If True, skip Pydantic validation. Use for
                progressive editing where entities are saved with incomplete data.
                Call validate_entity() separately to check for issues.

        Returns:
            The created Entity.

        Raises:
            EntityTypeNotFoundError: If entity_type not found in profile.
            ValidationError: If data fails schema validation (unless skip_validation=True).

        Example:
            >>> inv = client.create_entity("Investigation", {
            ...     "unique_id": "INV-001",
            ...     "title": "My Study"
            ... })

            >>> # Create draft with incomplete data
            >>> draft = client.create_entity(
            ...     "Investigation",
            ...     {"title": "Work in progress"},
            ...     skip_validation=True,
            ... )
        """
        self._validate_entity_type(entity_type)
        node = self._facade.add_entity(
            entity_type, data, parent_id=parent_id, skip_validation=skip_validation
        )
        return self._convert_node(node)

    def get_entity(self: Self, entity_id: str) -> Entity:
        """Get an entity by its ID.

        Args:
            entity_id: The entity ID to retrieve.

        Returns:
            The Entity if found.

        Raises:
            EntityNotFoundError: If entity not found.
        """
        node = self._facade.get_entity(entity_id)
        if node is None:
            raise EntityNotFoundError(entity_id)
        return self._convert_node(node)

    def update_entity(
        self: Self,
        entity_id: str,
        data: dict[str, Any],
        skip_validation: bool = False,
    ) -> Entity:
        """Update an existing entity's data.

        Replaces all field values with the provided data.
        By default, the entity is validated against the schema after update.

        Args:
            entity_id: ID of the entity to update.
            data: New field values.
            skip_validation: If True, skip Pydantic validation.

        Returns:
            The updated Entity.

        Raises:
            EntityNotFoundError: If entity not found.

        Example:
            >>> client.update_entity(inv.id, {
            ...     "unique_id": "INV-001",
            ...     "title": "Updated Title"
            ... })
        """
        node = self._facade.update_entity(entity_id, data, skip_validation)
        if node is None:
            raise EntityNotFoundError(entity_id)
        return self._convert_node(node)

    def delete_entity(self: Self, entity_id: str) -> None:
        """Delete an entity and all its children.

        Recursively deletes the entity and any entities that have it
        as their parent.

        Args:
            entity_id: ID of the entity to delete.

        Raises:
            EntityNotFoundError: If entity not found.
        """
        if not self._facade.delete_entity(entity_id):
            raise EntityNotFoundError(entity_id)

    # ========================================================================
    # Tree Operations
    # ========================================================================

    def get_tree(self: Self) -> list[EntityNode]:
        """Get the entity tree starting from root nodes.

        Returns a hierarchical tree structure with all entities.

        Returns:
            List of root EntityNodes with their children.
        """
        tree_dicts = self._facade.get_tree()
        return [self._dict_to_node(d) for d in tree_dicts]

    def get_children(self: Self, entity_id: str) -> list[EntityNode]:
        """Get direct children of an entity.

        Args:
            entity_id: ID of the parent entity.

        Returns:
            List of child EntityNodes.
        """
        nodes = self._facade.get_children(entity_id)
        return [self._convert_to_entity_node(n) for n in nodes]

    def get_roots(self: Self) -> list[EntityNode]:
        """Get all root entities (entities without parents).

        Returns:
            List of root EntityNodes.
        """
        nodes = self._facade.get_roots()
        return [self._convert_to_entity_node(n) for n in nodes]

    def get_entity_label(self: Self, entity_id: str) -> str:
        """Get the display label for an entity.

        Args:
            entity_id: ID of the entity.

        Returns:
            Display label string.

        Raises:
            EntityNotFoundError: If entity not found.
        """
        node = self._facade.get_entity(entity_id)
        if node is None:
            raise EntityNotFoundError(entity_id)

        helper = self._facade.get_helper(node.entity_type)
        if helper and node.instance:
            return helper.get_label(node.instance)
        return node.label

    # ========================================================================
    # Serialization
    # ========================================================================

    def serialize(self: Self, format: str = "flat") -> dict[str, Any]:
        """Serialize all entities to a dictionary.

        Returns a structure that can be saved to JSON/YAML and later
        loaded back with load().

        Args:
            format: Output format - "flat" (default) or "tree".
                - "flat": List of entities with _type and _parent_unique_id
                - "tree": Nested hierarchy with id, entity_type, label, data, children

        Returns:
            Dictionary with profile info and entity data.

        Example:
            >>> data = client.serialize()  # flat format
            >>> data = client.serialize(format="tree")  # nested tree
            >>> with open("dataset.json", "w") as f:
            ...     json.dump(data, f)
        """
        base = {
            "profile": self._facade.profile,
            "version": self._facade.version,
        }

        if format == "tree":
            base["tree"] = self._serialize_tree()
        else:
            base["entities"] = self._facade.to_dict()

        return base

    def _serialize_tree(self: Self) -> list[dict[str, Any]]:
        """Serialize entities as nested tree structure."""
        roots = self._facade.get_roots()

        def node_to_tree(node: Any) -> dict[str, Any]:
            data = self._get_instance_data(node.instance)

            # Get label using helper
            helper = self._facade.get_helper(node.entity_type)
            if helper and node.instance:
                label = helper.get_label(node.instance)
            else:
                label = node.label

            return {
                "id": node.id,
                "entity_type": node.entity_type,
                "label": label,
                "data": data,
                "children": [node_to_tree(c) for c in node.children],
            }

        return [node_to_tree(r) for r in roots]

    def load(self: Self, data: dict[str, Any]) -> int:
        """Load entities from serialized data.

        Clears existing entities and loads from the provided data.
        Auto-detects format (flat with "entities" or nested "tree").

        Args:
            data: Serialized data from serialize() or entity list directly.

        Returns:
            Number of entities loaded.

        Example:
            >>> with open("dataset.json") as f:
            ...     data = json.load(f)
            >>> client.load(data)  # auto-detects format
        """
        # Auto-detect format: tree vs flat
        if "tree" in data:
            return self._load_tree(data["tree"])

        if "entities" in data:
            entities = data["entities"]
        else:
            entities = data if isinstance(data, list) else []

        return self._facade.load_from_dict(entities)

    def _load_tree(self: Self, tree: list[dict[str, Any]]) -> int:
        """Load entities from nested tree format."""
        self._facade.clear()
        count = 0

        def load_node(node: dict[str, Any], parent_id: str | None = None) -> None:
            nonlocal count
            entity_type = node["entity_type"]
            data = node.get("data", {})
            node_id = node.get("id")

            self._facade.add_entity(
                entity_type,
                data,
                node_id=node_id,
                parent_id=parent_id,
                skip_validation=True,
            )
            count += 1

            for child in node.get("children", []):
                load_node(child, parent_id=node_id)

        for root in tree:
            load_node(root)

        return count

    def load_yaml(self: Self, path: str) -> int:
        """Load entities from a YAML dataset file.

        Args:
            path: Path to the YAML file containing entity data.

        Returns:
            Number of entities loaded.

        Example:
            >>> client.load_yaml("my-dataset.yaml")
        """
        return self._facade.load_yaml(path)

    def clear(self: Self) -> None:
        """Clear all entities from the client."""
        self._facade.clear()

    # ========================================================================
    # Validation
    # ========================================================================

    def validate(self: Self) -> ValidationResult:
        """Validate all entities.

        Runs validation on all entities in the store.

        Returns:
            ValidationResult with any issues found.
        """
        from metaseed.validators import validate_entity

        all_issues: list[ValidationIssue] = []

        # Iterate over all entities via get_roots and recursion
        def validate_node(node: Any) -> None:
            data = self._get_instance_data(node.instance)
            if not data:
                return

            errors = validate_entity(
                data,
                entity_type=node.entity_type,
                profile=self._facade.profile,
                version=self._facade.version,
            )

            for err in errors:
                all_issues.append(
                    ValidationIssue(
                        field=f"{node.id}.{err.field}",
                        message=err.message,
                        rule=err.rule,
                    )
                )

            for child in node.children:
                validate_node(child)

        for root in self._facade.get_roots():
            validate_node(root)

        if all_issues:
            return ValidationResult.failure(all_issues)
        return ValidationResult.success()

    def validate_entity(self: Self, entity_id: str) -> ValidationResult:
        """Validate a specific entity.

        Args:
            entity_id: ID of the entity to validate.

        Returns:
            ValidationResult for the entity.

        Raises:
            EntityNotFoundError: If entity not found.
        """
        from metaseed.validators import validate_entity as validate_fn

        node = self._facade.get_entity(entity_id)
        if node is None:
            raise EntityNotFoundError(entity_id)

        data = self._get_instance_data(node.instance)

        errors = validate_fn(
            data,
            entity_type=node.entity_type,
            profile=self._facade.profile,
            version=self._facade.version,
        )

        issues = [
            ValidationIssue(field=err.field, message=err.message, rule=err.rule) for err in errors
        ]

        if issues:
            return ValidationResult.failure(issues)
        return ValidationResult.success()

    # ========================================================================
    # Schema Introspection
    # ========================================================================

    def list_entity_types(self: Self) -> list[str]:
        """List all entity types in the profile.

        Returns:
            List of entity type names.

        Example:
            >>> client.list_entity_types()
            ['Investigation', 'Study', 'Person', 'Sample', ...]
        """
        return self._facade.entities

    def get_entity_fields(self: Self, entity_type: str) -> list[FieldInfo]:
        """Get field information for an entity type.

        Args:
            entity_type: Name of the entity type.

        Returns:
            List of FieldInfo objects describing each field.

        Raises:
            EntityTypeNotFoundError: If entity type not found.

        Example:
            >>> fields = client.get_entity_fields("Investigation")
            >>> for f in fields:
            ...     print(f"{f.name}: {f.type} {'(required)' if f.required else ''}")
        """
        self._validate_entity_type(entity_type)
        helper = getattr(self._facade, entity_type)

        fields = []
        for field_name in helper.all_fields:
            info = helper.field_info(field_name)
            fields.append(
                FieldInfo(
                    name=info["name"],
                    type=info["type"],
                    required=info["required"],
                    description=info.get("description", ""),
                    ontology_term=info.get("ontology_term"),
                    items=info.get("items"),
                    constraints=info.get("constraints"),
                )
            )
        return fields

    def get_entity_schema(self: Self, entity_type: str) -> EntitySchema:
        """Get complete schema information for an entity type.

        Args:
            entity_type: Name of the entity type.

        Returns:
            EntitySchema with full schema information.

        Raises:
            EntityTypeNotFoundError: If entity type not found.
        """
        self._validate_entity_type(entity_type)
        helper = getattr(self._facade, entity_type)

        fields = tuple(self.get_entity_fields(entity_type))

        return EntitySchema(
            name=helper.name,
            description=helper.description,
            ontology_term=helper.ontology_term,
            fields=fields,
            required_fields=tuple(helper.required_fields),
            optional_fields=tuple(helper.optional_fields),
        )

    # ========================================================================
    # Properties
    # ========================================================================

    @property
    def profile(self: Self) -> str:
        """Profile name."""
        return self._facade.profile

    @property
    def version(self: Self) -> str:
        """Profile version."""
        return self._facade.version

    @property
    def facade(self: Self) -> Any:
        """Access to underlying ProfileFacade for advanced use cases.

        This provides access to the internal ProfileFacade for scenarios
        that require direct facade access (e.g., UI routes, interactive use).
        Prefer using MetaseedClient methods when possible.

        Returns:
            The underlying ProfileFacade instance.
        """
        return self._facade

    def get_model(self: Self, entity_type: str) -> Any:
        """Get the Pydantic model class for an entity type.

        Provides access to the underlying model class for validation
        or advanced use cases.

        Args:
            entity_type: Name of the entity type.

        Returns:
            The Pydantic model class.

        Raises:
            EntityTypeNotFoundError: If entity type not found.
        """
        self._validate_entity_type(entity_type)
        helper = getattr(self._facade, entity_type)
        return helper._model

    # ========================================================================
    # Private Helpers
    # ========================================================================

    def _get_instance_data(self: Self, instance: Any) -> dict[str, Any]:
        """Extract data dictionary from a model instance.

        Args:
            instance: Pydantic model instance or None.

        Returns:
            Data dictionary or empty dict if instance is None/invalid.
        """
        if instance and hasattr(instance, "model_dump"):
            return instance.model_dump(exclude_none=True)
        return {}

    def _validate_entity_type(self: Self, entity_type: str) -> None:
        """Validate that an entity type exists in the profile."""
        if entity_type not in self._facade.entities:
            # Try case-insensitive match
            for name in self._facade.entities:
                if name.lower() == entity_type.lower():
                    return
            raise EntityTypeNotFoundError(entity_type, self._facade.profile)

    def _convert_node(self: Self, node: InternalEntityNode) -> Entity:
        """Convert internal EntityNode to public Entity."""
        return Entity(
            id=node.id,
            entity_type=node.entity_type,
            data=self._get_instance_data(node.instance),
            parent_id=node.parent_id,
        )

    def _convert_to_entity_node(self: Self, node: InternalEntityNode) -> EntityNode:
        """Convert internal EntityNode to public EntityNode."""
        return EntityNode(
            id=node.id,
            entity_type=node.entity_type,
            label=node.label,
            has_children=bool(node.children),
            children=[self._convert_to_entity_node(c) for c in node.children],
        )

    def _dict_to_node(self: Self, d: dict[str, Any]) -> EntityNode:
        """Convert tree dict to EntityNode."""
        return EntityNode(
            id=d["id"],
            entity_type=d["entity_type"],
            label=d["label"],
            has_children=d.get("has_children", False),
            children=[self._dict_to_node(c) for c in d.get("children", [])],
        )

    def __repr__(self: Self) -> str:
        """Return string representation."""
        return f"<MetaseedClient: {self._facade.profile} v{self._facade.version}>"
