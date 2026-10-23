"""Saving a row's own form writes the dataset (#356).

The nested form changed the row in the session and answered "Saved", but only
the open record's own Save wrote the dataset. A record added in a table and
saved from its own form was gone when the dataset was next opened.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

_DATASET = "miappe-1_2-example"


def _session() -> tuple[AppState, TestClient]:
    state = AppState()
    return state, TestClient(create_app(state), follow_redirects=True)


def _events_when_reopened() -> dict[str, dict]:
    state, client = _session()
    client.get(f"/dataset/{_DATASET}/edit")
    return {
        n.instance.unique_id: n.instance.model_dump(exclude_none=True)
        for n in state.nodes_by_id.values()
        if n.entity_type == "Event"
    }


def test_a_row_saved_from_its_own_form_is_there_when_reopened() -> None:
    state, client = _session()
    client.get("/load-example/miappe/1.2")
    study = next(n for n in state.nodes_by_id.values() if n.entity_type == "Study")
    client.get(f"/form/Study/{study.id}")
    row = len(state.current_nested_items["events"])
    client.post(
        "/table/Study/events/row", headers={"HX-Target": "inline-table-body-events"}
    )
    client.get(f"/nested/Study/events/{row}")

    response = client.post(
        f"/nested/Study/events/{row}",
        data={
            "unique_id": "EVT-ADDED",
            "event_type": "Irrigation",
            "date": "2026-01-01",
        },
    )

    assert response.status_code == 200
    events = _events_when_reopened()
    assert "EVT-ADDED" in events, (
        "the saved record is gone when the dataset is reopened"
    )
    assert events["EVT-ADDED"]["event_type"] == "Irrigation"
    assert events["EVT-ADDED"]["study_id"] == study.instance.unique_id


def test_an_edit_saved_from_a_stored_rows_form_is_there_when_reopened() -> None:
    state, client = _session()
    client.get("/load-example/miappe/1.2")
    study = next(n for n in state.nodes_by_id.values() if n.entity_type == "Study")
    client.get(f"/form/Study/{study.id}")
    first = state.current_nested_items["events"][0]
    event_id = first["unique_id"]
    client.get("/nested/Study/events/0")

    client.post(
        "/nested/Study/events/0",
        data={"unique_id": event_id, "event_type": "Changed in its own form"},
    )

    assert _events_when_reopened()[event_id]["event_type"] == "Changed in its own form"
