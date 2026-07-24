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
