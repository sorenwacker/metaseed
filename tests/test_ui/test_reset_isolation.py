"""Isolation + hermetic-reset guards for the (flaky) selenium suite.

These network-free tests lock in the two fixes that de-flake selenium: dataset
storage is redirectable to a throwaway dir, and ``/reset`` fully returns to a
clean overview (clearing the current-dataset pointer the manager tracks
separately from the state).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.repositories.filesystem_dataset import (
    FilesystemDatasetRepository,
    default_datasets_dir,
)
from metaseed.ui.app import create_app
from metaseed.ui.dataset_manager import resolve_dataset_manager
from metaseed.ui.state import AppState


def test_datasets_dir_honors_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    assert default_datasets_dir() == tmp_path
    # A repository built with no explicit dir uses the override.
    assert FilesystemDatasetRepository()._dir == tmp_path


def test_datasets_dir_defaults_without_env(monkeypatch):
    monkeypatch.delenv("METASEED_DATASETS_DIR", raising=False)
    assert str(default_datasets_dir()).endswith("metaseed/datasets")


def test_reset_clears_current_dataset_pointer():
    # A reset must clear the current dataset on BOTH the state and its manager,
    # else the overview keeps showing a stale selection between tests.
    state = AppState()
    app = create_app(state)
    client = TestClient(app)

    manager = resolve_dataset_manager(app, state)
    manager.current_dataset = "leftover"
    state._current_dataset = "leftover"  # type: ignore[attr-defined]

    response = client.post("/reset")

    assert response.status_code == 200
    assert manager.current_dataset is None
    assert getattr(state, "_current_dataset", None) is None


def test_polling_the_graph_keeps_the_current_dataset_pointer(
    tmp_path, monkeypatch
) -> None:
    """Reloading for a poll must not forget which dataset is open.

    ``/api/graph`` and ``/api/validate`` reload from disk on every tick, which
    goes through ``_restore_state_from_data`` -> ``AppState.reset()``. Since
    reset clears the current-dataset pointer, the next auto-save fell back to a
    label-derived name and wrote the user's edit into a *different* file.
    """
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from metaseed.ui.app import create_app
    from metaseed.ui.datasets import get_current_dataset_name
    from metaseed.ui.state import AppState

    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/pride/1.0")
    assert get_current_dataset_name(state) == "pride-1_0-example"

    client.get("/api/graph")

    assert get_current_dataset_name(state) == "pride-1_0-example", (
        "polling the graph forgot the open dataset; the next save would go elsewhere"
    )
