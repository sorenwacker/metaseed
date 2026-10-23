"""A pattern on a list of strings applies to each item (#337).

The model factory passed ``pattern`` to the list annotation, and Pydantic
refused it the first time an entity was created: "Unable to apply constraint
'pattern' ... for schema of type 'list'". The profile itself loaded, so the
problem surfaced only with the first dataset.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metaseed.models.factory import create_model_from_spec
from metaseed.specs.schema import EntitySpec, FieldSpec

_ORCID = r"^https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]$"


def _agent():
    return create_model_from_spec(
        EntitySpec(
            name="Agent",
            version="1.0",
            fields=[
                FieldSpec(
                    name="agent_identifier",
                    type="list",
                    items="string",
                    description="ORCIDs of the agent.",
                    constraints={"pattern": _ORCID, "min_items": 1},
                )
            ],
        )
    )


def test_a_conforming_list_validates() -> None:
    agent = _agent()(agent_identifier=["https://orcid.org/0000-0002-1825-0097"])

    assert agent.agent_identifier == ["https://orcid.org/0000-0002-1825-0097"]


def test_an_item_that_does_not_match_is_reported_as_that_item() -> None:
    with pytest.raises(ValidationError) as caught:
        _agent()(
            agent_identifier=["https://orcid.org/0000-0002-1825-0097", "not an orcid"]
        )

    (error,) = caught.value.errors()
    assert error["loc"] == ("agent_identifier", 1)


def test_the_list_keeps_its_own_cardinality() -> None:
    with pytest.raises(ValidationError):
        _agent()(agent_identifier=[])


def test_a_pattern_on_a_list_of_numbers_is_refused_with_the_field_named() -> None:
    with pytest.raises(ValueError, match="counts"):
        FieldSpec(
            name="counts",
            type="list",
            items="integer",
            description="",
            constraints={"pattern": r"^\d+$"},
        )
