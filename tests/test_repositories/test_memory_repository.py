"""Tests for MemoryEntityRepository."""

from __future__ import annotations

import pytest

from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.state import AppState


@pytest.fixture(autouse=True)
def _no_disk_autosave(monkeypatch):
    """Keep the repo hermetic — do not persist to the datasets dir."""
    monkeypatch.setattr("metaseed.ui.datasets.auto_save", lambda state: None)


def test_update_entity_returns_post_update_data():
    """update_entity must return the updated entity, not the pre-update snapshot.

    Regression: the method serialized the node fetched before the update, so the
    returned EntityData carried stale field values (REVIEW.md high finding).
    """
    repo = MemoryEntityRepository(AppState())  # default miappe profile
    created = repo.create_entity(
        "investigation", {"unique_id": "INV001", "title": "Old title"}
    )

    updated = repo.update_entity(created.id, {"title": "New title"})

    assert updated.data.get("title") == "New title"
