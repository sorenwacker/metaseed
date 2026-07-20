"""Tests for MemoryEntityRepository."""

from __future__ import annotations

from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.state import AppState

# The repository takes no on_change callback in these tests, so it never
# autosaves — the CRUD assertions run purely in-memory, no disk writes.


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
