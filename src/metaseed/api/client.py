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

    # ========================================================================
    # Entity CRUD Operations
    # ========================================================================

    def create_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str | None = None,
    ) -> Entity:
        """Create a new entity instance.

        Creates an entity of the specified type with the provided data.
        The entity is validated against the schema during creation.

        Args:
            entity_type: Type of entity to create (e.g., "Investigation").
            data: Field values for the entity.
            parent_id: Optional parent entity ID for hierarchical linking.

        Returns:
            The created Entity.

        Raises:
            EntityTypeNotFoundError: If entity_type not found in profile.
            ValidationError: If data fails schema validation.

        Example:
            >>> inv = client.create_entity("Investigation", {
            ...     "unique_id": "INV-001",
            ...     "title": "My Study"
            ... })
        """
        self._validate_entity_type(entity_type)
        node = self._facade.add_entity(entity_type, data, parent_id=parent_id)
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

    def update_entity(self: Self, entity_id: str, data: dict[str, Any]) -> Entity:
        """Update an existing entity's data.

        Replaces all field values with the provided data.
        The entity is validated against the schema after update.

        Args:
            entity_id: ID of the entity to update.
            data: New field values.

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
        node = self._facade.update_entity(entity_id, data)
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

    # ========================================================================
    # Serialization
    # ========================================================================

    def serialize(self: Self) -> dict[str, Any]:
        """Serialize all entities to a dictionary.

        Returns a structure that can be saved to JSON/YAML and later
        loaded back with load().

        Returns:
            Dictionary with profile info and entity data.

        Example:
            >>> data = client.serialize()
            >>> with open("dataset.json", "w") as f:
            ...     json.dump(data, f)
        """
        return {
            "profile": self._facade.profile,
            "version": self._facade.version,
            "entities": self._facade.to_dict(),
        }

    def load(self: Self, data: dict[str, Any]) -> int:
        """Load entities from serialized data.

        Clears existing entities and loads from the provided data.

        Args:
            data: Serialized data from serialize() or entity list directly.

        Returns:
            Number of entities loaded.

        Example:
            >>> with open("dataset.json") as f:
            ...     data = json.load(f)
            >>> client.load(data)
        """
        # Support both full serialize() output and direct entity list
        if "entities" in data:
            entities = data["entities"]
        else:
            entities = data if isinstance(data, list) else []

        return self._facade.load_from_dict(entities)

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

        for node in self._facade._store._instances.values():
            if node.instance and hasattr(node.instance, "model_dump"):
                data = node.instance.model_dump(exclude_none=True)
            else:
                continue

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

        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)
        else:
            data = {}

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

    # ========================================================================
    # Private Helpers
    # ========================================================================

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
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)
        else:
            data = {}

        return Entity(
            id=node.id,
            entity_type=node.entity_type,
            data=data,
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
