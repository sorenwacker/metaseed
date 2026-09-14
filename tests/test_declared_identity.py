"""#143: declared identifier/label resolution replaces positional guessing.

Each listed entity previously mis-resolved its identifier or label to a nested
model or a parent reference. With ``is_identifier``/``is_label`` markers declared
in the specs, ``EntityHelper.identifier_field`` and ``derive_label`` must resolve
to the sensible scalar field instead.
"""

from __future__ import annotations

import pytest

from metaseed.facade.core import ProfileFacade
from metaseed.repositories.helpers import derive_label

# (profile, version, entity, resolved_field, a decoy field that used to win)
_CASES = [
    ("isa", "1.0", "FactorValue", "value", "factor_name"),
    ("isa", "1.0", "Characteristic", "value", "category"),
    ("isa", "1.0", "ParameterValue", "value", "category"),
    ("isa", "1.0", "Protocol", "name", "study_id"),
    ("isa", "1.0", "Source", "name", "study_id"),
    ("isa", "1.0", "Sample", "name", "study_id"),
    ("isa", "1.0", "StudyFactor", "name", "study_id"),
    ("isa", "1.0", "DataFile", "filename", "assay_id"),
    ("ena", "1.0", "File", "filename", "run_ref"),
]


@pytest.mark.parametrize(("profile", "version", "entity", "resolved", "decoy"), _CASES)
def test_identifier_and_label_resolve_to_declared_field(
    profile: str, version: str, entity: str, resolved: str, decoy: str
) -> None:
    helper = getattr(ProfileFacade(profile, version), entity)

    # identifier_field is the declared scalar, not a nested model / reference.
    assert helper.identifier_field == resolved

    # derive_label picks the declared field's value even when the decoy field
    # (a nested ref or parent id) also carries a value.
    data = {resolved: "REAL", decoy: "DECOY"}
    assert derive_label(entity, data, spec=helper._spec) == "REAL"


def _labelled_entity(label_type: str, items: str | None = None):
    """An entity whose declared label field has ``label_type``, after a parent reference and a note."""
    from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType

    return EntityDefSpec(
        fields=[
            FieldSpec(name="parent_id", type=FieldType.STRING, reference="Parent.id"),
            FieldSpec(name="note", type=FieldType.STRING),
            FieldSpec(
                name="label_field",
                type=FieldType(label_type),
                items=items,
                is_label=True,
            ),
        ]
    )


class TestDeclaredLabelOfTypedValues:
    """A declared label labels the entity whether its value is raw or validated.

    Validation turns ``uri``, ``date`` and ``datetime`` values into ``AnyUrl``
    and date objects; those used to be rejected as labels, so a validated
    entity fell back to another field or to ``New <Entity>``.
    """

    def test_a_uri_value_labels_as_its_text(self) -> None:
        from pydantic import AnyUrl

        spec = _labelled_entity("uri")
        data = {
            "parent_id": "P1",
            "note": "NOTE",
            "label_field": AnyUrl("https://example.org/agents/1"),
        }
        assert derive_label("Agent", data, spec=spec) == "https://example.org/agents/1"

    def test_a_datetime_value_labels_as_iso_8601(self) -> None:
        import datetime

        spec = _labelled_entity("datetime")
        value = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
        data = {"parent_id": "P1", "note": "NOTE", "label_field": value}
        assert derive_label("Period", data, spec=spec) == "2020-01-01T00:00:00+00:00"

    def test_a_date_value_labels_as_iso_8601(self) -> None:
        import datetime

        spec = _labelled_entity("date")
        data = {
            "parent_id": "P1",
            "note": "NOTE",
            "label_field": datetime.date(2020, 1, 1),
        }
        assert derive_label("Period", data, spec=spec) == "2020-01-01"

    def test_a_declared_list_labels_by_its_first_entry(self) -> None:
        spec = _labelled_entity("list", items="string")
        data = {
            "parent_id": "P1",
            "note": "NOTE",
            "label_field": ["Example Institute", "Voorbeeld Instituut"],
        }
        assert derive_label("Agent", data, spec=spec) == "Example Institute"

    def test_an_empty_declared_list_is_a_new_entity(self) -> None:
        spec = _labelled_entity("list", items="string")
        data = {"parent_id": "P1", "note": "NOTE", "label_field": []}
        assert derive_label("Agent", data, spec=spec) == "New Agent"

    def test_an_undeclared_first_list_field_is_not_the_label(self) -> None:
        from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType

        spec = EntityDefSpec(
            fields=[
                FieldSpec(name="names", type=FieldType.LIST, items="string"),
                FieldSpec(name="code", type=FieldType.STRING),
            ]
        )
        data = {"names": ["A", "B"], "code": "C1"}
        assert derive_label("Thing", data, spec=spec) == "C1"
