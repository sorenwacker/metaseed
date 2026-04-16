"""Pydantic models for MIAPPE specification schema.

This module defines the structure of YAML specification files that describe
MIAPPE entities and their fields.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict


class FieldType(StrEnum):
    """Supported field types in profile specifications.

    These types map to Python/Pydantic types in the model factory.
    """

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    URI = "uri"
    ONTOLOGY_TERM = "ontology_term"
    LIST = "list"
    ENTITY = "entity"  # Reference to another entity (single object)


class Constraints(BaseModel):
    """Field constraints for validation.

    Attributes:
        pattern: Regex pattern for string validation.
        min_length: Minimum string length.
        max_length: Maximum string length.
        minimum: Minimum numeric value.
        maximum: Maximum numeric value.
        enum: List of allowed values for enumerated fields.
    """

    model_config = ConfigDict(extra="forbid")

    pattern: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    enum: list[str] | None = None


class FieldSpec(BaseModel):
    """Specification for a single field in an entity.

    Attributes:
        name: Field identifier (snake_case).
        type: Data type of the field.
        required: Whether the field is mandatory.
        description: Human-readable description.
        ontology_term: Reference to ontology term (e.g., MIAPPE:DM-1).
        constraints: Validation constraints.
        items: For list type, the entity type of list items.
        parent_ref: Parent entity reference in format "Entity.field" (e.g., "Study.identifier").
            Fields with parent_ref are auto-filled from parent context and hidden in nested forms.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: FieldType
    required: bool = False
    description: str = ""
    ontology_term: str | None = None
    constraints: Constraints | None = None
    items: str | None = None
    parent_ref: str | None = None


class EntitySpec(BaseModel):
    """Specification for a MIAPPE entity.

    Attributes:
        name: Entity name (PascalCase).
        version: MIAPPE version (e.g., "1.1").
        ontology_term: Reference to PPEO ontology term.
        description: Human-readable description.
        fields: List of field specifications.
        example: Example values for this entity (for documentation and testing).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    ontology_term: str | None = None
    description: str = ""
    fields: list[FieldSpec] = []
    example: dict[str, str | int | float | bool | list] | None = None

    def get_required_fields(self: Self) -> list[FieldSpec]:
        """Return list of required fields.

        Returns:
            List of FieldSpec objects where required is True.
        """
        return [f for f in self.fields if f.required]

    def get_optional_fields(self: Self) -> list[FieldSpec]:
        """Return list of optional fields.

        Returns:
            List of FieldSpec objects where required is False.
        """
        return [f for f in self.fields if not f.required]


class EntityDefSpec(BaseModel):
    """Entity definition within a unified profile spec.

    Similar to EntitySpec but without name/version (inherited from profile).
    """

    model_config = ConfigDict(extra="forbid")

    ontology_term: str | None = None
    description: str = ""
    fields: list[FieldSpec] = []
    example: dict[str, str | int | float | bool | list] | None = None


class ValidationRuleSpec(BaseModel):
    """Validation rule definition in profile spec.

    Attributes:
        name: Rule identifier.
        description: What the rule checks.
        applies_to: List of entity names or "all".
        field: Field the rule applies to (optional).
        condition: Rule condition expression.
        pattern: Regex pattern for pattern rules.
        minimum: Minimum value for numeric range rules.
        maximum: Maximum value for numeric range rules.
        enum: Allowed values for vocabulary rules.
        reference: Entity.field reference for integrity rules.
        unique_within: Scope for uniqueness rules (e.g., "parent").
        min_items: Minimum items for list cardinality rules.
        max_items: Maximum items for list cardinality rules.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    applies_to: list[str] | str = "all"
    field: str | None = None
    condition: str | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    enum: list[str] | None = None
    reference: str | None = None
    unique_within: str | None = None
    min_items: int | None = None
    max_items: int | None = None


class ProfileSpec(BaseModel):
    """Unified profile specification containing all entities.

    A profile spec defines a complete metadata standard (e.g., MIAPPE v1.1)
    in a single YAML file.

    Attributes:
        version: Profile version (e.g., "1.1").
        name: Profile name (e.g., "MIAPPE").
        display_name: Human-friendly name for UI (e.g., "MIAPPE").
        description: Description of the profile.
        ontology: Base ontology used (e.g., "PPEO").
        root_entity: Primary entity type for this profile (e.g., "Investigation").
        validation_rules: Cross-entity validation rules.
        entities: Dictionary of entity name to definition.
    """

    model_config = ConfigDict(extra="forbid")

    version: str
    name: str
    display_name: str | None = None
    description: str = ""
    ontology: str | None = None
    root_entity: str = "Investigation"
    validation_rules: list[ValidationRuleSpec] = []
    entities: dict[str, EntityDefSpec] = {}

    def _to_pascal_case(self: Self, name: str) -> str:
        """Convert snake_case to PascalCase.

        Args:
            name: Name in snake_case (e.g., "biological_material").

        Returns:
            Name in PascalCase (e.g., "BiologicalMaterial").
        """
        return "".join(word.capitalize() for word in name.split("_"))

    def get_entity(self: Self, entity_name: str) -> EntitySpec:
        """Get an EntitySpec for a specific entity.

        Args:
            entity_name: Name of the entity (snake_case or PascalCase).

        Returns:
            EntitySpec with name and version populated.

        Raises:
            KeyError: If entity not found.
        """
        # Try exact match first
        if entity_name in self.entities:
            entity_def = self.entities[entity_name]
            return EntitySpec(
                name=entity_name,
                version=self.version,
                ontology_term=entity_def.ontology_term,
                description=entity_def.description,
                fields=entity_def.fields,
                example=entity_def.example,
            )

        # Try PascalCase conversion (for snake_case input)
        pascal_name = self._to_pascal_case(entity_name)
        if pascal_name in self.entities:
            entity_def = self.entities[pascal_name]
            return EntitySpec(
                name=pascal_name,
                version=self.version,
                ontology_term=entity_def.ontology_term,
                description=entity_def.description,
                fields=entity_def.fields,
                example=entity_def.example,
            )

        # Try case-insensitive match
        for name, entity_def in self.entities.items():
            if name.lower() == entity_name.lower():
                return EntitySpec(
                    name=name,
                    version=self.version,
                    ontology_term=entity_def.ontology_term,
                    description=entity_def.description,
                    fields=entity_def.fields,
                    example=entity_def.example,
                )

        raise KeyError(f"Entity '{entity_name}' not found in profile {self.name} v{self.version}")

    def list_entities(self: Self) -> list[str]:
        """List all entity names in the profile.

        Returns:
            List of entity names.
        """
        return list(self.entities.keys())
