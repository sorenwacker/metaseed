"""The file repository stores the parent field a child was created for (ADR 006).

A SEEK Study holds Persons in ``person_responsible``, ``experimentalists`` and
``creators``. Before the field was recorded, a reloaded experimentalist was
re-derived from its type and filed as the person responsible.
"""

from __future__ import annotations

import pytest

from metaseed.repositories.file import FileEntityRepository


def _repo(tmp_path) -> FileEntityRepository:
    return FileEntityRepository(
        dataset_path=tmp_path / "test-parent-field.json", profile="seek", version="1.0"
    )


def _study(repo: FileEntityRepository):
    investigation = repo.create_entity(
        "Investigation",
        {"identifier": "INV-1", "project_id": "1", "title": "I", "description": "I"},
    )
    return repo.create_entity(
        "Study",
        {"identifier": "STU-1", "title": "S", "description": "S"},
        parent_id=investigation.id,
    )


def test_the_parent_field_survives_a_reload(tmp_path) -> None:
    repo = _repo(tmp_path)
    study = _study(repo)
    person = repo.create_entity(
        "Person",
        {"identifier": "P-1", "first_name": "Ada", "last_name": "Example"},
        parent_id=study.id,
        parent_field="experimentalists",
    )

    reloaded = _repo(tmp_path)

    assert reloaded.get_entity(person.id).parent_field == "experimentalists"
    assert reloaded.get_entity(study.id).data.get("experimentalists") == ["P-1"]
    assert not reloaded.get_entity(study.id).data.get("person_responsible")


def test_an_ambiguous_parent_field_is_rejected(tmp_path) -> None:
    repo = _repo(tmp_path)
    study = _study(repo)

    with pytest.raises(ValueError, match="experimentalists"):
        repo.create_entity(
            "Person",
            {"identifier": "P-1", "first_name": "Ada", "last_name": "Example"},
            parent_id=study.id,
        )
