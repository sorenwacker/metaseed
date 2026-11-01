"""Reloading the open dataset from disk keeps the edit in progress.

The graph panel polls /api/graph every two seconds, and the route reloads the
dataset from disk to pick up changes made by an MCP agent. The reload went
through a full state reset, which also forgot the record open in the form and
the rows of its nested tables: the first poll after opening an Investigation
emptied its studies, and the Edit button on a Study row then answered
"Row not found" and did nothing. The existing nested-route test never polled.

Keeping the rows as they were is not enough either: the poll exists to pick up
an agent's changes, and rows restored unreconciled made the next form save
recreate a child the agent had deleted and overwrite one it had edited.
See docs/guides/embedding-the-graph.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.dataset_manager import DatasetManager, resolve_dataset_manager
from metaseed.ui.datasets import set_current_dataset_name
from metaseed.ui.state import AppState

DATASET = "test-isa-trial"


@pytest.fixture
def opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AppState, TestClient, DatasetManager]:
    """An ISA example saved as a dataset, opened from the list, root form open."""
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    state = AppState()
    app = create_app(state)
    client = TestClient(app, follow_redirects=True)
    assert client.get("/load-example/isa/1.0").status_code == 200
    manager = resolve_dataset_manager(app, state)
    manager.save_dataset(DATASET)
    assert client.get(f"/dataset/{DATASET}/edit").status_code == 200
    root = next(n for n in state.nodes_by_id.values() if n.parent_id is None)
    assert client.get(f"/form/{root.entity_type}/{root.id}").status_code == 200
    assert state.current_nested_items["studies"]
    return state, client, manager


def agent_for(manager: DatasetManager) -> tuple[AppState, DatasetManager]:
    """A second session on the same repository, as an MCP agent would have."""
    agent_state = AppState()
    agent = DatasetManager(manager.repository, agent_state)
    agent.load_dataset(DATASET)
    return agent_state, agent


def study_ids(state: AppState) -> list[str]:
    return [row["_node_id"] for row in state.current_nested_items["studies"]]


def test_the_study_edit_button_still_works_after_a_poll(opened) -> None:
    _, client, _ = opened

    assert client.get("/api/graph").status_code == 200

    response = client.get("/nested/Investigation/studies/0")
    assert response.status_code == 200, response.text


def test_the_poll_keeps_the_record_open_in_the_form(opened) -> None:
    state, client, _ = opened
    editing = state.editing_node_id

    client.get("/api/graph")

    assert state.editing_node_id == editing
    assert state.current_nested_items["studies"]


def test_a_study_deleted_on_disk_leaves_the_table_and_is_not_recreated(
    opened,
) -> None:
    state, client, manager = opened
    gone = study_ids(state)[0]
    agent_state, agent = agent_for(manager)
    assert agent_state.delete_node(gone)
    agent.save_dataset(DATASET)

    client.get("/api/graph")

    assert gone not in study_ids(state)
    response = client.put(
        f"/entity/{state.editing_node_id}",
        data={"identifier": "test-investigation", "title": "Kept"},
    )
    assert response.status_code == 200, response.text
    assert gone not in state.nodes_by_id


def test_a_study_edited_on_disk_shows_the_new_value(opened) -> None:
    state, client, manager = opened
    changed = study_ids(state)[0]
    agent_state, agent = agent_for(manager)
    data = agent_state.nodes_by_id[changed].instance.model_dump(exclude_none=True)
    data["title"] = "Renamed by the agent"
    agent_state.update_node(changed, data)
    agent.save_dataset(DATASET)

    client.get("/api/graph")

    row = next(
        r for r in state.current_nested_items["studies"] if r["_node_id"] == changed
    )
    assert row["title"] == "Renamed by the agent"


def test_a_study_added_on_disk_gains_a_row(opened) -> None:
    state, client, manager = opened
    before = study_ids(state)
    agent_state, agent = agent_for(manager)
    added = agent_state.add_node(
        "Study",
        {"identifier": "test-added-study", "title": "Added by the agent"},
        parent_id=state.editing_node_id,
        parent_field="studies",
    )
    agent.save_dataset(DATASET)

    client.get("/api/graph")

    assert study_ids(state) == [*before, added.id]


def test_an_unsaved_cell_edit_survives_the_poll(opened) -> None:
    state, client, _ = opened
    response = client.post(
        "/table/Investigation/studies/row/0/cell", data={"title": "Typed, not saved"}
    )
    assert response.status_code == 200

    client.get("/api/graph")

    assert state.current_nested_items["studies"][0]["title"] == "Typed, not saved"


def test_an_unsaved_added_row_survives_the_poll(opened) -> None:
    state, client, _ = opened
    before = len(state.current_nested_items["studies"])
    assert client.post("/table/Investigation/studies/row").status_code == 200

    client.get("/api/graph")

    assert len(state.current_nested_items["studies"]) == before + 1


def test_a_row_deleted_in_the_browser_stays_deleted(opened) -> None:
    state, client, _ = opened
    removed = study_ids(state)[0]
    assert client.delete("/table/Investigation/studies/row/0").status_code == 200

    client.get("/api/graph")

    assert removed not in study_ids(state)


def test_the_nested_chain_is_cut_when_its_row_vanishes(opened) -> None:
    state, client, manager = opened
    assert client.get("/nested/Investigation/studies/0").status_code == 200
    assert state.nested_edit_stack
    gone = study_ids(state)[0]
    agent_state, agent = agent_for(manager)
    assert agent_state.delete_node(gone)
    agent.save_dataset(DATASET)

    client.get("/api/graph")

    assert state.nested_edit_stack == []


def test_the_nested_chain_survives_when_its_row_is_unchanged(opened) -> None:
    state, client, _ = opened
    assert client.get("/nested/Investigation/studies/0").status_code == 200
    stack = list(state.nested_edit_stack)

    client.get("/api/graph")

    assert state.nested_edit_stack == stack


def test_opening_another_dataset_forgets_the_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    state = AppState()
    app = create_app(state)
    client = TestClient(app, follow_redirects=True)
    assert client.get("/load-example/isa/1.0").status_code == 200
    manager = resolve_dataset_manager(app, state)
    manager.save_dataset("test-isa-a")
    manager.save_dataset("test-isa-b")
    assert client.get("/dataset/test-isa-a/edit").status_code == 200
    root = next(n for n in state.nodes_by_id.values() if n.parent_id is None)
    assert client.get(f"/form/{root.entity_type}/{root.id}").status_code == 200
    assert state.editing_node_id == root.id

    assert client.get("/dataset/test-isa-b/edit").status_code == 200

    assert state.editing_node_id is None
    assert state.current_nested_items == {}


def test_a_dataset_the_ui_manager_last_loaded_is_not_a_reload_of_the_open_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MCP load tool moves only the state's pointer, through a fresh manager.

    The UI manager then still names the dataset it loaded last. Opening that
    one is a change of dataset, not a reload, even though the manager's own
    pointer matches: accepting it carried the open edit's rows into it.
    """
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    state = AppState()
    app = create_app(state)
    client = TestClient(app, follow_redirects=True)
    assert client.get("/load-example/isa/1.0").status_code == 200
    manager = resolve_dataset_manager(app, state)
    manager.save_dataset("test-isa-a")
    manager.save_dataset("test-isa-b")
    assert client.get("/dataset/test-isa-b/edit").status_code == 200
    DatasetManager(manager.repository, state).load_dataset("test-isa-a")
    set_current_dataset_name(state, "test-isa-a")
    root = next(n for n in state.nodes_by_id.values() if n.parent_id is None)
    assert client.get(f"/form/{root.entity_type}/{root.id}").status_code == 200
    assert state.current_nested_items["studies"]

    response = client.post("/api/datasets/load", json={"name": "test-isa-b"})

    assert response.status_code == 200, response.text
    assert state.editing_node_id is None
    assert state.current_nested_items == {}
