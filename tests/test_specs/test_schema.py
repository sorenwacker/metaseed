"""Tests for spec schema models."""

import pytest
from pydantic import ValidationError

from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    OntologyDefinition,
    ProfileSpec,
    SeekEntityConfig,
)


class TestSeekEntityConfig:
    """Tests for the SEEK export role config on entities."""

    def test_accepts_a_known_role(self) -> None:
        assert SeekEntityConfig(role="ObservationUnit").role == "ObservationUnit"

    def test_rejects_an_unknown_role(self) -> None:
        # A hand-authored/merged profile with a typo must fail at load, not
        # silently export a nonexistent jerm: class.
        with pytest.raises(ValidationError):
            SeekEntityConfig(role="studdy")  # type: ignore[arg-type]

    def test_role_round_trips_through_entity_yaml(self) -> None:
        entity = EntityDefSpec(seek=SeekEntityConfig(role="Sample"))
        dumped = entity.model_dump(exclude_none=True)
        assert dumped["seek"] == {"role": "Sample"}
        assert EntityDefSpec.model_validate(dumped).seek.role == "Sample"


class TestConstraints:
    """Tests for Constraints model."""

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

    def test_is_nested_entity_type(self) -> None:
        """Entity type fields are nested."""
        field = FieldSpec(
            name="location",
            type=FieldType.ENTITY,
            description="Location entity",
            items="Location",
        )
        assert field.is_nested() is True

    def test_is_nested_list_of_entities(self) -> None:
        """List of entities is nested."""
        field = FieldSpec(
            name="studies",
            type=FieldType.LIST,
            description="List of studies",
            items="Study",
        )
        assert field.is_nested() is True

    def test_is_nested_list_of_strings_not_nested(self) -> None:
        """List of strings is not nested."""
        field = FieldSpec(
            name="tags",
            type=FieldType.LIST,
            description="List of tags",
            items="string",
        )
        assert field.is_nested() is False

    @pytest.mark.parametrize(
        "scalar_type",
        [
            "string",
            "integer",
            "float",
            "boolean",
            "date",
            "datetime",
            "uri",
            "ontology_term",
        ],
    )
    def test_is_nested_list_of_scalar_not_nested(self, scalar_type: str) -> None:
        """List of any canonical scalar type is not nested."""
        field = FieldSpec(
            name="values",
            type=FieldType.LIST,
            description="List of scalars",
            items=scalar_type,
        )
        assert field.is_nested() is False

    def test_is_nested_list_of_entity_type_nested(self) -> None:
        """List whose items name an entity type is nested."""
        field = FieldSpec(
            name="studies",
            type=FieldType.LIST,
            description="List of studies",
            items="Study",
        )
        assert field.is_nested() is True

    def test_is_nested_string_type_not_nested(self) -> None:
        """String type is not nested."""
        field = FieldSpec(
            name="title",
            type=FieldType.STRING,
            description="Title",
        )
        assert field.is_nested() is False

    def test_is_nested_list_without_items_not_nested(self) -> None:
        """List without items spec is not nested."""
        field = FieldSpec(
            name="items",
            type=FieldType.LIST,
            description="Generic list",
        )
        assert field.is_nested() is False

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

    def test_ontology_term_field_with_ontologies(self) -> None:
        """Ontology term field can specify which ontologies to search."""
        field = FieldSpec(
            name="tissue",
            type=FieldType.ONTOLOGY_TERM,
            ontologies=["po"],
            description="Plant tissue from Plant Ontology",
        )
        assert field.ontologies == ["po"]

    def test_ontology_term_field_with_multiple_ontologies(self) -> None:
        """Ontology term field can specify multiple ontologies."""
        field = FieldSpec(
            name="trait",
            type=FieldType.ONTOLOGY_TERM,
            ontologies=["pato", "to"],
            description="Trait from PATO or Trait Ontology",
        )
        assert field.ontologies == ["pato", "to"]

    def test_ontologies_defaults_to_none(self) -> None:
        """Ontologies field defaults to None when not specified."""
        field = FieldSpec(
            name="term",
            type=FieldType.ONTOLOGY_TERM,
            description="Any ontology term",
        )
        assert field.ontologies is None


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


class TestOntologyDefinition:
    """Tests for OntologyDefinition model."""

    def test_full_definition(self) -> None:
        """OntologyDefinition with all fields."""
        ont = OntologyDefinition(
            name="Plant Ontology",
            uri="http://purl.obolibrary.org/obo/po.owl",
            ols_id="po",
        )
        assert ont.name == "Plant Ontology"
        assert ont.uri == "http://purl.obolibrary.org/obo/po.owl"
        assert ont.ols_id == "po"

    def test_minimal_definition(self) -> None:
        """OntologyDefinition with only required name field."""
        ont = OntologyDefinition(name="Custom Ontology")
        assert ont.name == "Custom Ontology"
        assert ont.uri is None
        assert ont.ols_id is None

    def test_missing_name_raises(self) -> None:
        """Missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            OntologyDefinition(uri="http://example.org")

    def test_extra_fields_forbidden(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError):
            OntologyDefinition(name="Test", extra_field="value")


class TestProfileSpecVersioning:
    """Tests for ProfileSpec spec_version and ontologies fields."""

    def test_default_spec_version(self) -> None:
        """ProfileSpec defaults to spec_version 0.1."""
        profile = ProfileSpec(
            name="test",
            version="1.0",
            entities={
                "Sample": EntityDefSpec(
                    fields=[
                        FieldSpec(name="id", type=FieldType.STRING, required=True),
                    ]
                )
            },
        )
        assert profile.spec_version == "0.1"

    def test_explicit_spec_version(self) -> None:
        """ProfileSpec with explicit spec_version."""
        profile = ProfileSpec(
            spec_version="0.2",
            name="test",
            version="1.0",
            entities={},
        )
        assert profile.spec_version == "0.2"

    def test_ontologies_section(self) -> None:
        """ProfileSpec with ontologies section."""
        profile = ProfileSpec(
            spec_version="0.2",
            name="test",
            version="1.0",
            ontologies={
                "OBI": OntologyDefinition(
                    name="Ontology for Biomedical Investigations",
                    uri="http://purl.obolibrary.org/obo/obi.owl",
                    ols_id="obi",
                ),
                "ENVO": OntologyDefinition(
                    name="Environment Ontology",
                    ols_id="envo",
                ),
            },
            entities={},
        )
        assert profile.ontologies is not None
        assert len(profile.ontologies) == 2
        assert (
            profile.ontologies["OBI"].name == "Ontology for Biomedical Investigations"
        )
        assert profile.ontologies["OBI"].ols_id == "obi"
        assert profile.ontologies["ENVO"].ols_id == "envo"

    def test_ontologies_defaults_to_none(self) -> None:
        """ProfileSpec without ontologies section has None."""
        profile = ProfileSpec(
            name="test",
            version="1.0",
            entities={},
        )
        assert profile.ontologies is None

    def test_profile_with_ontology_and_ontologies(self) -> None:
        """ProfileSpec can have both ontology and ontologies fields."""
        profile = ProfileSpec(
            spec_version="0.2",
            name="test",
            version="1.0",
            ontology="PPEO",
            ontologies={
                "PPEO": OntologyDefinition(
                    name="Plant Phenotyping Experiment Ontology",
                    ols_id="ppeo",
                ),
            },
            entities={},
        )
        assert profile.ontology == "PPEO"
        assert profile.ontologies["PPEO"].ols_id == "ppeo"


class TestFieldMarkers:
    """Tests for the #137/#143/#98 relationship-role and metadata markers."""

    def test_new_markers_default_to_none(self) -> None:
        # None defaults keep un-migrated specs byte-stable under exclude_none.
        f = FieldSpec(name="x", type=FieldType.STRING)
        assert f.owns is None
        assert f.is_identifier is None
        assert f.is_label is None
        assert f.example is None
        assert f.options is None
        assert f.unit is None
        assert f.label is None
        assert f.tier is None

    def test_markers_round_trip(self) -> None:
        f = FieldSpec(
            name="value",
            type=FieldType.STRING,
            is_identifier=True,
            is_label=True,
            example="42",
            options=["a", "b"],
            unit="cm",
            label="Value",
            tier="recommended",
        )
        dumped = f.model_dump(exclude_none=True)
        restored = FieldSpec.model_validate(dumped)
        assert restored == f

    def test_owns_marker_on_relationship(self) -> None:
        f = FieldSpec(name="studies", type=FieldType.LIST, items="Study", owns=True)
        assert f.owns is True
        assert f.is_nested() is True

    def test_tier_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            FieldSpec(name="x", type=FieldType.STRING, tier="mandatory")  # type: ignore[arg-type]

    def test_two_identifier_fields_rejected_entitydef(self) -> None:
        # Authoring guard: at most one is_identifier per entity.
        with pytest.raises(ValidationError):
            EntityDefSpec(
                fields=[
                    FieldSpec(name="a", type=FieldType.STRING, is_identifier=True),
                    FieldSpec(name="b", type=FieldType.STRING, is_identifier=True),
                ]
            )

    def test_two_label_fields_rejected_entitydef(self) -> None:
        with pytest.raises(ValidationError):
            EntityDefSpec(
                fields=[
                    FieldSpec(name="a", type=FieldType.STRING, is_label=True),
                    FieldSpec(name="b", type=FieldType.STRING, is_label=True),
                ]
            )

    def test_single_identifier_field_accepted(self) -> None:
        ed = EntityDefSpec(
            fields=[
                FieldSpec(name="a", type=FieldType.STRING, is_identifier=True),
                FieldSpec(name="b", type=FieldType.STRING),
            ]
        )
        assert ed.fields[0].is_identifier is True

    def test_unknown_field_key_still_forbidden(self) -> None:
        # extra="forbid" must still reject typos even with the new optional keys.
        with pytest.raises(ValidationError):
            FieldSpec(name="x", type=FieldType.STRING, ownz=True)  # type: ignore[call-arg]
