"""The MCP tools place a child in the parent field the caller names (ADR 006)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from metaseed.agent.mcp.server import create_server, set_mcp_state
from metaseed.ui.state import AppState
from tests.test_agent.helpers import get_tool

PERSON = {"identifier": "P-1", "first_name": "Ada", "last_name": "Example"}


@pytest.fixture
def study():
    state = AppState(profile="seek", version="1.0")
    set_mcp_state(state)
    server = create_server()
    create = get_tool(server, "create_entity")
    with patch("metaseed.ui.datasets.auto_save"):
        investigation = json.loads(
            create(
                entity_type="Investigation",
                data=json.dumps(
                    {
                        "identifier": "INV-1",
                        "project_id": "1",
                        "title": "I",
                        "description": "I",
                    }
                ),
            )
        )
        created = json.loads(
            create(
                entity_type="Study",
                data=json.dumps(
                    {"identifier": "STU-1", "title": "S", "description": "S"}
                ),
                parent_id=investigation["id"],
            )
        )
        yield server, state, created["id"]


def _study_data(state: AppState, study_id: str) -> dict:
    return state.get_or_create_facade().get_entity(study_id).instance.model_dump()


def test_create_entity_writes_the_named_field(study) -> None:
    server, state, study_id = study

    answer = json.loads(
        get_tool(server, "create_entity")(
            entity_type="Person",
            data=json.dumps(PERSON),
            parent_id=study_id,
            parent_field="experimentalists",
        )
    )

    assert answer["linked_via_field"] == "experimentalists", answer
    assert _study_data(state, study_id)["experimentalists"] == ["P-1"]
    assert not _study_data(state, study_id).get("person_responsible")


def test_create_entity_names_the_candidates_when_the_field_is_ambiguous(study) -> None:
    server, _state, study_id = study

    answer = get_tool(server, "create_entity")(
        entity_type="Person", data=json.dumps(PERSON), parent_id=study_id
    )

    assert "person_responsible" in answer and "experimentalists" in answer, answer


def test_batch_create_reads_parent_field_from_each_spec(study) -> None:
    server, state, study_id = study

    get_tool(server, "batch_create")(
        entities=json.dumps(
            [
                {
                    "entity_type": "Person",
                    "data": PERSON,
                    "parent_id": study_id,
                    "parent_field": "creators",
                }
            ]
        )
    )

    assert _study_data(state, study_id)["creators"] == ["P-1"]
