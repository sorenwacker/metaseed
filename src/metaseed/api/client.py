"""Public API client for metaseed.

This module provides MetaseedClient, a clean entry point for working with
metadata schemas and entities. It wraps ProfileFacade and provides a
stable public interface.

Example:
    >>> from metaseed import MetaseedClient
    >>> client = MetaseedClient("miappe", "1.2")
    >>> client.list_entity_types()
    ['Investigation', 'Study', 'Person', ...]
    >>> inv = client.create_entity(
    ...     "Investigation",
    ...     {"unique_id": "INV-001", "title": "My Study"}
    ... )
    >>> client.validate()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic import ValidationError as PydanticValidationError

from metaseed.api.entities import Entity, EntityNode
from metaseed.api.errors import (
    EntityNotFoundError,
    EntityTypeNotFoundError,
    InvalidSpecError,
    ProfileNotFoundError,
    ValidationError,
)
from metaseed.api.schema import EntitySchema, FieldInfo
from metaseed.api.serialization import SerializationMixin
from metaseed.api.validation import ValidationMixin

if TYPE_CHECKING:
    from metaseed.facade import EntityNode as InternalEntityNode
    from metaseed.facade import ProfileFacade
    from metaseed.specs.schema import ProfileSpec


class MetaseedClient(SerializationMixin, ValidationMixin):
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

    _facade: ProfileFacade

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
            ...             "fields": [
            ...                 {"name": "id", "type": "string", "required": True}
            ...             ]
            ...         }
            ...     }
            ... }
            >>> client = MetaseedClient.from_spec(spec)
        """
        from metaseed.facade import ProfileFacade
        from metaseed.specs.loader import SpecLoadError
        from metaseed.specs.schema import ProfileSpec as ProfileSpecCls

        try:
            if isinstance(spec, dict):
                spec = ProfileSpecCls(
                    **spec
                )  # pydantic ValidationError is a ValueError
            instance = cls.__new__(cls)
            instance._facade = ProfileFacade(spec.name, spec=spec)
        except (ValueError, SpecLoadError) as e:
            raise InvalidSpecError(str(e)) from e
        return instance

    @classmethod
    def from_facade(cls, facade: ProfileFacade) -> MetaseedClient:
        """Wrap an already-configured ``ProfileFacade`` in a client.

        Lets a consumer that already holds a facade (for example metaseed-hub's
        ``AppState.facade``) reuse the client's serialization and validation
        instead of reimplementing them, without reaching into a private field.

        Args:
            facade: The ``ProfileFacade`` to wrap.

        Returns:
            A :class:`MetaseedClient` backed by the given facade.
        """
        instance = cls.__new__(cls)
        instance._facade = facade
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
        import yaml

        from metaseed.facade import ProfileFacade
        from metaseed.specs.loader import SpecLoadError

        try:
            instance = cls.__new__(cls)
            instance._facade = ProfileFacade.from_yaml(path)
        except (OSError, ValueError, SpecLoadError, yaml.YAMLError) as e:
            raise InvalidSpecError(str(e)) from e
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
        By default, the entity is validated against the schema.

        Args:
            entity_type: Type of entity to create (e.g., "Investigation").
            data: Field values for the entity.
            parent_id: Optional parent entity ID for hierarchical linking.
            skip_validation: If True, skip Pydantic validation.

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
        entity_type = self._validate_entity_type(entity_type)
        try:
            node = self._facade.add_entity(
                entity_type, data, parent_id=parent_id, skip_validation=skip_validation
            )
        except PydanticValidationError as e:
            raise self._translate_validation_error(e) from e
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

        Args:
            entity_id: ID of the entity to update.
            data: New field values.
            skip_validation: If True, skip Pydantic validation.

        Returns:
            The updated Entity.

        Raises:
            EntityNotFoundError: If entity not found.
            ValidationError: If data fails schema validation.

        Example:
            >>> client.update_entity(inv.id, {
            ...     "unique_id": "INV-001",
            ...     "title": "Updated Title"
            ... })
        """
        try:
            node = self._facade.update_entity(entity_id, data, skip_validation)
        except PydanticValidationError as e:
            raise self._translate_validation_error(e) from e
        if node is None:
            raise EntityNotFoundError(entity_id)
        return self._convert_node(node)

    def delete_entity(self: Self, entity_id: str) -> None:
        """Delete an entity and all its children.

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
            ...     print(f"{f.name}: {f.type}")
        """
        entity_type = self._validate_entity_type(entity_type)
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
                    example=info.get("example"),
                    options=info.get("options"),
                    unit=info.get("unit"),
                    label=info.get("label"),
                    tier=info.get("tier"),
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
        entity_type = self._validate_entity_type(entity_type)
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

        Returns:
            The underlying ProfileFacade instance.
        """
        return self._facade

    def get_model(self: Self, entity_type: str) -> Any:
        """Get the Pydantic model class for an entity type.

        Args:
            entity_type: Name of the entity type.

        Returns:
            The Pydantic model class.

        Raises:
            EntityTypeNotFoundError: If entity type not found.
        """
        entity_type = self._validate_entity_type(entity_type)
        helper = getattr(self._facade, entity_type)
        return helper.model

    # ========================================================================
    # Private Helpers
    # ========================================================================

    @staticmethod
    def _translate_validation_error(
        error: PydanticValidationError,
    ) -> ValidationError:
        """Translate a pydantic ValidationError into the public ValidationError.

        Args:
            error: The pydantic validation error raised by model construction.

        Returns:
            A public ``metaseed.api.errors.ValidationError`` carrying structured
            per-field error details.
        """
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "rule": err["type"],
            }
            for err in error.errors()
        ]
        return ValidationError(errors)

    def _validate_entity_type(self: Self, entity_type: str) -> str:
        """Validate an entity type and return its canonical name.

        Entity types are matched case-insensitively, but the canonical
        (exact-case) name from the profile is returned so callers store and
        query entities consistently.

        Args:
            entity_type: The entity type name to validate, in any casing.

        Returns:
            The canonical entity-type name as defined in the profile.

        Raises:
            EntityTypeNotFoundError: If no entity type matches, ignoring case.
        """
        if entity_type in self._facade.entities:
            return entity_type
        for name in self._facade.entities:
            if name.lower() == entity_type.lower():
                return name
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
