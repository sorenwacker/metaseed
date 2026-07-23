"""Tests for MemoryEntityRepository."""

from __future__ import annotations

import pytest

from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.state import AppState

# The repository takes no on_change callback in these tests, so it never
# autosaves — the CRUD assertions run purely in-memory, no disk writes.


def test_tree_linker_allows_only_owned_children():
    """The parent-child gate uses child_fields, not every nested field (#137).

    isa Assay marks its containment fields ``owns: true`` and leaves its
    OntologyAnnotation lookups unmarked, so a DataFile (owned) may nest under an
    Assay but an OntologyAnnotation (a lookup) may not.
    """
    repo = MemoryEntityRepository(AppState(profile="isa", version="1.0"))
    inv = repo.create_entity("Investigation", {"identifier": "I1", "title": "t"})
    study = repo.create_entity(
        "Study", {"identifier": "S1", "title": "t"}, parent_id=inv.id
    )
    assay = repo.create_entity("Assay", {"filename": "a_x.txt"}, parent_id=study.id)

    owned = repo.create_entity("DataFile", {"filename": "d_x.txt"}, parent_id=assay.id)
    assert owned.data.get("filename") == "d_x.txt"

    with pytest.raises(ValueError, match="cannot contain OntologyAnnotation"):
        repo.create_entity("OntologyAnnotation", {"term": "x"}, parent_id=assay.id)


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
