"""Tests for model factory."""

import datetime

import pytest
from pydantic import BaseModel, ValidationError

from miappe_api.models.factory import create_model_from_spec
from miappe_api.specs.schema import Constraints, EntitySpec, FieldSpec, FieldType


class TestCreateModelFromSpec:
    """Tests for create_model_from_spec function."""

    def test_create_simple_model(self) -> None:
        """Create a model with basic string fields."""
        spec = EntitySpec(
            name="Simple",
            version="1.0",
            description="Simple test entity",
            fields=[
                FieldSpec(
                    name="name",
                    type=FieldType.STRING,
                    required=True,
                    description="Name",
                ),
            ],
        )

        Model = create_model_from_spec(spec)

        assert Model.__name__ == "Simple"
        instance = Model(name="test")
        assert instance.name == "test"

    def test_required_fields_enforced(self) -> None:
        """Required fields must be provided."""
        spec = EntitySpec(
            name="WithRequired",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="required_field",
                    type=FieldType.STRING,
                    required=True,
                    description="Required",
                ),
            ],
        )

        Model = create_model_from_spec(spec)

        with pytest.raises(ValidationError) as exc_info:
            Model()
        assert "required_field" in str(exc_info.value)

    def test_optional_fields_default_none(self) -> None:
        """Optional fields default to None."""
        spec = EntitySpec(
            name="WithOptional",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="optional_field",
                    type=FieldType.STRING,
                    required=False,
                    description="Optional",
                ),
            ],
        )

        Model = create_model_from_spec(spec)
        instance = Model()
        assert instance.optional_field is None

    def test_all_field_types(self) -> None:
        """All supported field types are mapped correctly."""
        spec = EntitySpec(
            name="AllTypes",
            version="1.0",
            description="Test all types",
            fields=[
                FieldSpec(name="str_field", type=FieldType.STRING, description=""),
                FieldSpec(name="int_field", type=FieldType.INTEGER, description=""),
                FieldSpec(name="float_field", type=FieldType.FLOAT, description=""),
                FieldSpec(name="bool_field", type=FieldType.BOOLEAN, description=""),
                FieldSpec(name="date_field", type=FieldType.DATE, description=""),
                FieldSpec(name="datetime_field", type=FieldType.DATETIME, description=""),
                FieldSpec(name="uri_field", type=FieldType.URI, description=""),
                FieldSpec(name="onto_field", type=FieldType.ONTOLOGY_TERM, description=""),
            ],
        )

        Model = create_model_from_spec(spec)
        instance = Model(
            str_field="test",
            int_field=42,
            float_field=3.14,
            bool_field=True,
            date_field="2024-01-15",
            datetime_field="2024-01-15T10:30:00",
            uri_field="https://example.com",
            onto_field="GO:0001234",
        )

        assert instance.str_field == "test"
        assert instance.int_field == 42
        assert instance.float_field == 3.14
        assert instance.bool_field is True
        assert instance.date_field == datetime.date(2024, 1, 15)
        assert instance.datetime_field == datetime.datetime(2024, 1, 15, 10, 30, 0)
        assert str(instance.uri_field) == "https://example.com/"
        assert instance.onto_field == "GO:0001234"

    def test_list_field_type(self) -> None:
        """List fields are mapped correctly."""
        spec = EntitySpec(
            name="WithList",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="items",
                    type=FieldType.LIST,
                    items="string",
                    required=False,
                    description="List of strings",
                ),
            ],
        )

        Model = create_model_from_spec(spec)
        instance = Model(items=["a", "b", "c"])
        assert instance.items == ["a", "b", "c"]

    def test_string_constraints_pattern(self) -> None:
        """String pattern constraint is enforced."""
        spec = EntitySpec(
            name="WithPattern",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType.STRING,
                    required=True,
                    description="ID",
                    constraints=Constraints(pattern=r"^[A-Z]+$"),
                ),
            ],
        )

        Model = create_model_from_spec(spec)

        instance = Model(id="ABC")
        assert instance.id == "ABC"

        with pytest.raises(ValidationError):
            Model(id="abc123")

    def test_string_constraints_min_max_length(self) -> None:
        """String length constraints are enforced."""
        spec = EntitySpec(
            name="WithLength",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="name",
                    type=FieldType.STRING,
                    required=True,
                    description="Name",
                    constraints=Constraints(min_length=2, max_length=10),
                ),
            ],
        )

        Model = create_model_from_spec(spec)

        instance = Model(name="test")
        assert instance.name == "test"

        with pytest.raises(ValidationError):
            Model(name="a")  # too short

        with pytest.raises(ValidationError):
            Model(name="abcdefghijk")  # too long

    def test_numeric_constraints_min_max(self) -> None:
        """Numeric constraints are enforced."""
        spec = EntitySpec(
            name="WithNumeric",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count",
                    type=FieldType.INTEGER,
                    required=True,
                    description="Count",
                    constraints=Constraints(minimum=0, maximum=100),
                ),
            ],
        )

        Model = create_model_from_spec(spec)

        instance = Model(count=50)
        assert instance.count == 50

        with pytest.raises(ValidationError):
            Model(count=-1)

        with pytest.raises(ValidationError):
            Model(count=101)

    def test_model_is_basemodel(self) -> None:
        """Generated model is a Pydantic BaseModel."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[],
        )

        Model = create_model_from_spec(spec)
        assert issubclass(Model, BaseModel)

    def test_model_has_json_schema(self) -> None:
        """Generated model has JSON schema."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType.STRING,
                    required=True,
                    description="ID field",
                ),
            ],
        )

        Model = create_model_from_spec(spec)
        schema = Model.model_json_schema()

        assert "properties" in schema
        assert "id" in schema["properties"]
        assert schema["properties"]["id"]["description"] == "ID field"

    def test_model_serialization(self) -> None:
        """Generated model can be serialized to dict and JSON."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="name",
                    type=FieldType.STRING,
                    required=True,
                    description="Name",
                ),
                FieldSpec(
                    name="count",
                    type=FieldType.INTEGER,
                    required=False,
                    description="Count",
                ),
            ],
        )

        Model = create_model_from_spec(spec)
        instance = Model(name="test", count=42)

        # To dict
        data = instance.model_dump()
        assert data == {"name": "test", "count": 42}

        # To JSON
        json_str = instance.model_dump_json()
        assert "test" in json_str
        assert "42" in json_str

    def test_nested_models_in_constructor(self) -> None:
        """Models can contain nested models in constructor."""
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")
        Person = get_model("Person")

        inv = Investigation(
            unique_id="INV-001",
            title="Test",
            contacts=[
                Person(name="Dr. Smith", email="smith@uni.edu", institution="Uni"),
            ],
            studies=[
                Study(unique_id="STU-001", title="Study 1"),
            ],
        )

        assert len(inv.contacts) == 1
        assert len(inv.studies) == 1
        assert inv.contacts[0].name == "Dr. Smith"
        assert inv.studies[0].unique_id == "STU-001"

    def test_list_fields_default_to_empty_list(self) -> None:
        """List fields default to empty list for easier use."""
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        inv = Investigation(unique_id="INV-001", title="Test")

        # Lists default to empty, not None
        assert inv.studies == []
        assert inv.contacts == []

    def test_list_fields_support_append(self) -> None:
        """List fields support standard Python operations."""
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")

        inv = Investigation(unique_id="INV-001", title="Test")
        inv.studies.append(Study(unique_id="STU-001", title="Study 1"))
        inv.studies.append(Study(unique_id="STU-002", title="Study 2"))

        assert len(inv.studies) == 2
        assert inv.studies[0].unique_id == "STU-001"
        assert inv.studies[1].unique_id == "STU-002"

    def test_deeply_nested_models(self) -> None:
        """Models support deep nesting following PPEO hierarchy."""
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")
        Factor = get_model("Factor")
        ObservedVariable = get_model("ObservedVariable")

        inv = Investigation(
            unique_id="INV-001",
            title="Test",
            studies=[
                Study(
                    unique_id="STU-001",
                    title="Study 1",
                    factors=[
                        Factor(unique_id="F-001", name="Water", description="Treatment"),
                    ],
                    observed_variables=[
                        ObservedVariable(
                            unique_id="VAR-001",
                            name="Plant Height",
                            trait="Height",
                            method="Ruler",
                            scale="cm",
                        ),
                    ],
                ),
            ],
        )

        assert len(inv.studies) == 1
        assert len(inv.studies[0].factors) == 1
        assert len(inv.studies[0].observed_variables) == 1
        assert inv.studies[0].factors[0].name == "Water"
        assert inv.studies[0].observed_variables[0].name == "Plant Height"
