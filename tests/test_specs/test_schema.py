"""Tests for spec schema models."""

import pytest
from pydantic import ValidationError

from miappe_api.specs.schema import (
    Constraints,
    EntitySpec,
    FieldSpec,
    FieldType,
)


class TestFieldType:
    """Tests for FieldType enum."""

    def test_all_types_defined(self) -> None:
        """All expected field types are defined."""
        expected = {
            "string",
            "integer",
            "float",
            "boolean",
            "date",
            "datetime",
            "uri",
            "ontology_term",
            "list",
            "entity",
        }
        actual = {t.value for t in FieldType}
        assert actual == expected


class TestConstraints:
    """Tests for Constraints model."""

    def test_empty_constraints(self) -> None:
        """Empty constraints are valid."""
        c = Constraints()
        assert c.pattern is None
        assert c.min_length is None
        assert c.max_length is None
        assert c.minimum is None
        assert c.maximum is None

    def test_string_constraints(self) -> None:
        """String constraints (pattern, min/max length) are parsed."""
        c = Constraints(
            pattern=r"^[A-Za-z0-9_-]+$",
            min_length=1,
            max_length=100,
        )
        assert c.pattern == r"^[A-Za-z0-9_-]+$"
        assert c.min_length == 1
        assert c.max_length == 100

    def test_numeric_constraints(self) -> None:
        """Numeric constraints (min/max) are parsed."""
        c = Constraints(minimum=0, maximum=1000)
        assert c.minimum == 0
        assert c.maximum == 1000


class TestFieldSpec:
    """Tests for FieldSpec model."""

    def test_required_field(self) -> None:
        """Required field with minimal properties."""
        field = FieldSpec(
            name="unique_id",
            type=FieldType.STRING,
            required=True,
            description="Unique identifier",
        )
        assert field.name == "unique_id"
        assert field.type == FieldType.STRING
        assert field.required is True
        assert field.description == "Unique identifier"
        assert field.ontology_term is None
        assert field.constraints is None
        assert field.items is None

    def test_optional_field(self) -> None:
        """Optional field with defaults."""
        field = FieldSpec(
            name="description",
            type=FieldType.STRING,
            description="Description text",
        )
        assert field.required is False  # default

    def test_field_with_ontology_term(self) -> None:
        """Field with ontology term reference."""
        field = FieldSpec(
            name="title",
            type=FieldType.STRING,
            required=True,
            description="Title",
            ontology_term="MIAPPE:0000001",
        )
        assert field.ontology_term == "MIAPPE:0000001"

    def test_field_with_constraints(self) -> None:
        """Field with constraints."""
        field = FieldSpec(
            name="unique_id",
            type=FieldType.STRING,
            required=True,
            description="Unique ID",
            constraints=Constraints(pattern=r"^[A-Za-z0-9_-]+$"),
        )
        assert field.constraints is not None
        assert field.constraints.pattern == r"^[A-Za-z0-9_-]+$"

    def test_list_field_with_items(self) -> None:
        """List field with items type."""
        field = FieldSpec(
            name="studies",
            type=FieldType.LIST,
            required=False,
            description="List of studies",
            items="Study",
        )
        assert field.type == FieldType.LIST
        assert field.items == "Study"

    def test_missing_name_raises(self) -> None:
        """Missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            FieldSpec(
                type=FieldType.STRING,
                description="Test",
            )

    def test_missing_type_raises(self) -> None:
        """Missing type raises ValidationError."""
        with pytest.raises(ValidationError):
            FieldSpec(
                name="test",
                description="Test",
            )


class TestEntitySpec:
    """Tests for EntitySpec model."""

    def test_valid_entity_spec(self) -> None:
        """Valid entity spec with all fields."""
        spec = EntitySpec(
            name="Investigation",
            version="1.1",
            ontology_term="ppeo:investigation",
            description="A phenotyping project",
            fields=[
                FieldSpec(
                    name="unique_id",
                    type=FieldType.STRING,
                    required=True,
                    description="Unique identifier",
                ),
                FieldSpec(
                    name="title",
                    type=FieldType.STRING,
                    required=True,
                    description="Title",
                ),
            ],
        )
        assert spec.name == "Investigation"
        assert spec.version == "1.1"
        assert spec.ontology_term == "ppeo:investigation"
        assert spec.description == "A phenotyping project"
        assert len(spec.fields) == 2

    def test_missing_name_raises(self) -> None:
        """Missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            EntitySpec(
                version="1.1",
                description="Test",
                fields=[],
            )

    def test_missing_version_raises(self) -> None:
        """Missing version raises ValidationError."""
        with pytest.raises(ValidationError):
            EntitySpec(
                name="Test",
                description="Test",
                fields=[],
            )

    def test_empty_fields_allowed(self) -> None:
        """Empty fields list is allowed."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test entity",
            fields=[],
        )
        assert spec.fields == []

    def test_get_required_fields(self) -> None:
        """Get required fields method works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="required_field",
                    type=FieldType.STRING,
                    required=True,
                    description="Required",
                ),
                FieldSpec(
                    name="optional_field",
                    type=FieldType.STRING,
                    required=False,
                    description="Optional",
                ),
            ],
        )
        required = spec.get_required_fields()
        assert len(required) == 1
        assert required[0].name == "required_field"

    def test_get_optional_fields(self) -> None:
        """Get optional fields method works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="required_field",
                    type=FieldType.STRING,
                    required=True,
                    description="Required",
                ),
                FieldSpec(
                    name="optional_field",
                    type=FieldType.STRING,
                    required=False,
                    description="Optional",
                ),
            ],
        )
        optional = spec.get_optional_fields()
        assert len(optional) == 1
        assert optional[0].name == "optional_field"
