"""A case-insensitively resolved entity type must be stored as resolved (260816).

`facade.require_helper` resolves entity types case-insensitively on purpose,
but both repositories then kept the caller's raw string. Everything downstream
compares with `==` against canonical spec names, so `create_entity("study", ...)`
was accepted by the resolver and immediately rejected as an invalid child of
Investigation. Worse, where the PARENT carried a non-canonical case, the
parent-reference lookups missed silently and the child was stored mis-linked
rather than refused.
"""

from __future__ import annotations

import pytest

from metaseed.repositories.file import FileEntityRepository
from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.state import AppState


def _memory() -> MemoryEntityRepository:
    return MemoryEntityRepository(AppState(profile="miappe", version="1.2"))


def _file(tmp_path) -> FileEntityRepository:
    return FileEntityRepository(
        dataset_path=tmp_path / "d.json", profile="miappe", version="1.2"
    )


@pytest.mark.parametrize("kind", ["memory", "file"])
def test_a_lowercase_child_type_is_accepted_under_its_parent(kind, tmp_path) -> None:
    repo = _memory() if kind == "memory" else _file(tmp_path)
    inv = repo.create_entity("Investigation", {"unique_id": "INV-1", "title": "I"})

    child = repo.create_entity(
        "study", {"unique_id": "STU-1", "title": "S"}, parent_id=inv.id
    )

    assert child.entity_type == "Study", "the raw caller string was stored"


@pytest.mark.parametrize("kind", ["memory", "file"])
def test_the_parent_reference_is_filled_for_a_lowercase_parent(kind, tmp_path) -> None:
    """The silent case: a mis-cased parent broke linking without any error."""
    repo = _memory() if kind == "memory" else _file(tmp_path)
    inv = repo.create_entity("investigation", {"unique_id": "INV-1", "title": "I"})

    child = repo.create_entity(
        "Study", {"unique_id": "STU-1", "title": "S"}, parent_id=inv.id
    )

    assert child.data.get("investigation_id") == "INV-1", child.data
