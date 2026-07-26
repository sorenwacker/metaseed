"""Tests for the shared field-form -> FieldSpec mapping (FieldForm)."""

from metaseed.specs.field_form import FieldForm
from metaseed.specs.schema import FieldSpec, FieldType


def test_to_field_spec_populates_scalars_and_constraints() -> None:
    field = FieldForm(
        name="  latitude  ",
        field_type="float",
        required=True,
        description=" the latitude ",
        ontology_term=" ENVO:1 ",
        ontologies="envo, pato\ngo",
        codename=" lat ",
        minimum="-90",
        maximum="90",
        pattern=r"\d+",
    ).to_field_spec()

    assert field.name == "latitude"
    assert field.type is FieldType.FLOAT
    assert field.required is True
    assert field.description == "the latitude"
    assert field.ontology_term == "ENVO:1"
    assert field.ontologies == ["envo", "pato", "go"]
    assert field.codename == "lat"
    assert field.constraints is not None
    assert field.constraints.minimum == -90.0
    assert field.constraints.maximum == 90.0
    assert field.constraints.pattern == r"\d+"


def test_markers_are_mapped_including_owns_and_tier() -> None:
    field = FieldForm(
        name="studies",
        field_type="list",
        items="Study",
        owns=True,
        tier="required",
        label="Studies",
        unit="count",
        example="STU-1",
        options="a, b ,c",
    ).to_field_spec()

    assert field.owns is True
    assert field.tier == "required"
    assert field.label == "Studies"
    assert field.unit == "count"
    assert field.example == "STU-1"
    assert field.options == ["a", "b", "c"]


def test_unset_markers_normalize_to_none() -> None:
    # Booleans off and empty strings must drop to None, not False/"".
    field = FieldForm(name="x", field_type="string").to_field_spec()
    assert field.owns is None
    assert field.is_identifier is None
    assert field.is_label is None
    assert field.tier is None
    assert field.label is None
    assert field.options is None
    assert field.constraints is None


def test_invalid_tier_is_dropped() -> None:
    field = FieldForm(name="x", tier="bogus").to_field_spec()
    assert field.tier is None


def test_apply_to_preserves_field_identity() -> None:
    existing = FieldSpec(name="old", type=FieldType.STRING)
    FieldForm(name="new", field_type="integer", is_identifier=True).apply_to(existing)
    assert existing.name == "new"
    assert existing.type is FieldType.INTEGER
    assert existing.is_identifier is True
