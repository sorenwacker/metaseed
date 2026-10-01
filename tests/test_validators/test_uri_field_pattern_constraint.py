"""A field-level ``pattern`` on a ``uri`` field is enforced, not fatal (#312).

The model factory handed the pattern to Pydantic, which cannot apply a regex to
``AnyUrl``: building the model raised for every value, valid or not. #139 had
already routed rule-level patterns on ``uri`` fields to the engine; the
field-level constraint took the other path and was missed. The type-by-constraint
test below covers every combination so a second path cannot hide the same way.
"""

from __future__ import annotations

import pytest
from pydantic import create_model

from metaseed import MetaseedClient
from metaseed.models.factory import _create_field_definition
from metaseed.specs.schema import Constraints, FieldSpec, FieldType

UUID_PATTERN = (
    r"(urn:uuid:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
VALID_UUID = "urn:uuid:69658110-5216-4e10-95c3-b1bdca2a1e52"

SPEC = {
    "version": "1.0",
    "name": "uri_pattern_probe",
    "root_entity": "Sample",
    "entities": {
        "Sample": {
            "fields": [
                {"name": "unique_id", "type": "string", "required": True},
                {
                    "name": "uuid",
                    "type": "uri",
                    "constraints": {"pattern": UUID_PATTERN},
                },
            ]
        }
    },
}


def _messages(client: MetaseedClient) -> list[str]:
    return [i.message for i in client.validate().issues]


def test_a_matching_uri_is_valid() -> None:
    client = MetaseedClient.from_spec(SPEC)
    client.create_entity("Sample", {"unique_id": "S1", "uuid": VALID_UUID})

    assert _messages(client) == []


def test_a_uri_that_does_not_match_is_reported() -> None:
    client = MetaseedClient.from_spec(SPEC)
    client.create_entity(
        "Sample",
        {"unique_id": "S1", "uuid": "https://example.org/sample/1"},
        skip_validation=True,
    )

    messages = _messages(client)

    assert len(messages) == 1, messages
    assert "uuid" in messages[0]


def test_an_absent_uri_passes() -> None:
    client = MetaseedClient.from_spec(SPEC)
    client.create_entity("Sample", {"unique_id": "S1"})

    assert _messages(client) == []


# A value of each type that satisfies the constraint alongside it.
_SATISFYING = {
    FieldType.STRING: "urn:uuid:1",
    FieldType.URI: "urn:uuid:1",
    FieldType.ONTOLOGY_TERM: "urn:uuid:1",
}
_STRING_CONSTRAINTS = [
    {"pattern": r"urn:uuid:\d"},
    {"min_length": 3},
    {"max_length": 80},
]


@pytest.mark.parametrize("field_type", list(_SATISFYING))
@pytest.mark.parametrize("constraint", _STRING_CONSTRAINTS, ids=lambda c: next(iter(c)))
def test_every_documented_constraint_accepts_a_satisfying_value(
    field_type: FieldType, constraint: dict
) -> None:
    field = FieldSpec(
        name="x", type=field_type, description="", constraints=Constraints(**constraint)
    )
    model = create_model("Probe", x=_create_field_definition(field))

    model(x=_SATISFYING[field_type])
