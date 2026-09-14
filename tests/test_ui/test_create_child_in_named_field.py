"""The edit form adds a child to one named parent field (ADR 006).

A SEEK Study holds Persons in three fields. The form offered one "+ Person"
button, and the new Person went into whichever field matched first, so every
experimentalist was saved as the person responsible.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

PERSON = {
    "_entity_type": "Person",
    "identifier": "P-1",
    "first_name": "Ada",
    "last_name": "Example",
}


def _client_with_study() -> tuple[TestClient, AppState, str]:
    state = AppState(profile="seek", version="1.0")
    client = TestClient(create_app(state))
    client.post(
        "/entity",
        data={
            "_entity_type": "Investigation",
            "identifier": "INV-1",
            "project_id": "1",
            "title": "I",
            "description": "I",
        },
    )
    investigation_id = state.editing_node_id
    client.post(
        "/entity",
        data={
            "_entity_type": "Study",
            "_parent_id": investigation_id,
            "identifier": "STU-1",
            "title": "S",
            "description": "S",
        },
    )
    return client, state, state.editing_node_id


def test_the_form_offers_one_add_button_per_field() -> None:
    client, _state, study_id = _client_with_study()

    html = client.get(f"/form/Study/{study_id}").text

    for field in ("person_responsible", "experimentalists", "creators"):
        assert f'data-testid="btn-add-child-{field}"' in html
        assert f"parent_field={field}" in html


def test_the_child_form_carries_the_field_it_was_opened_for() -> None:
    client, _state, study_id = _client_with_study()

    html = client.get(
        f"/form/child/{study_id}/Person?parent_field=experimentalists"
    ).text

    assert 'name="_parent_field"' in html
    assert 'value="experimentalists"' in html


def test_a_child_is_saved_into_the_named_field() -> None:
    client, state, study_id = _client_with_study()

    client.post(
        "/entity",
        data={**PERSON, "_parent_id": study_id, "_parent_field": "experimentalists"},
    )

    from metaseed.ui.helpers import get_nested_items_for_edit

    facade = state.get_or_create_facade()
    study = state.nodes_by_id[study_id]
    assert [c.parent_field for c in study.children] == ["experimentalists"]
    tables = get_nested_items_for_edit(study, facade.Study, facade)
    assert [row["identifier"] for row in tables["experimentalists"]] == ["P-1"]
    assert not tables.get("person_responsible")


def test_an_ambiguous_child_is_refused_with_the_candidates() -> None:
    client, state, study_id = _client_with_study()
    before = len(state.get_or_create_facade().get_entity(study_id).children)

    response = client.post("/entity", data={**PERSON, "_parent_id": study_id})

    assert "person_responsible" in response.text and "experimentalists" in response.text
    assert len(state.get_or_create_facade().get_entity(study_id).children) == before
