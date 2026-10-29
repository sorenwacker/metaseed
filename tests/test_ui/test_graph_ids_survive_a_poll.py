"""The graph's nodes keep their ids from one poll to the next.

The graph panel polls /api/graph every two seconds, the route reloads the
dataset from disk, and the browser matches nodes by id. Records stored with the
same ``_node_id`` (one copied into a second parent keeps the copy's id) were
given a random id on every load, so the graph removed and redrew them on every
poll. See docs/architecture/entity-repository.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.dataset_manager import resolve_dataset_manager
from metaseed.ui.state import AppState


def _with_a_copied_study(datasets: Path) -> None:
    """An ISA example whose first Study is copied, stored id and all."""
    state = AppState()
    app = create_app(state)
    client = TestClient(app, follow_redirects=True)
    assert client.get("/load-example/isa/1.0").status_code == 200
    resolve_dataset_manager(app, state).save_dataset("test-copied-study")
    path = datasets / "test-copied-study.json"
    data = json.loads(path.read_text())
    study = next(e for e in data["entities"] if e["_type"] == "Study")
    data["entities"].append(dict(study))
    path.write_text(json.dumps(data))


def test_a_repeated_stored_id_gives_the_same_nodes_on_every_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    _with_a_copied_study(tmp_path)
    state = AppState()
    app = create_app(state)
    client = TestClient(app)
    resolve_dataset_manager(app, state).load_dataset("test-copied-study")

    first = {n["id"] for n in client.get("/api/graph").json()["nodes"]}
    second = {n["id"] for n in client.get("/api/graph").json()["nodes"]}

    assert first == second
    studies = [
        n for n in client.get("/api/graph").json()["nodes"] if n["group"] == "Study"
    ]
    assert len({n["id"] for n in studies}) == len(studies) >= 2, (
        "the copy is its own node"
    )
