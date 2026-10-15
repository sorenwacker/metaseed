"""Every read of the memory repository reports a child's parent_field.

list_entities and get_entity built EntityData by hand and left parent_field
unset, while create/update/get_tree set it, so the same entity reported a
different field depending on which method fetched it.
"""

from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.state import AppState


def _repo_with_experimentalist() -> tuple[MemoryEntityRepository, str]:
    repo = MemoryEntityRepository(AppState(profile="seek", version="1.0"))
    investigation = repo.create_entity(
        "Investigation", {"identifier": "INV-1", "title": "I"}
    )
    study = repo.create_entity(
        "Study", {"identifier": "STU-1", "title": "S"}, parent_id=investigation.id
    )
    person = repo.create_entity(
        "Person",
        {"identifier": "P-1", "first_name": "Ada", "last_name": "Example"},
        parent_id=study.id,
        parent_field="experimentalists",
    )
    assert person.parent_field == "experimentalists"
    return repo, person.id


def test_list_entities_reports_the_parent_field() -> None:
    repo, _ = _repo_with_experimentalist()

    (person,) = repo.list_entities("Person")

    assert person.parent_field == "experimentalists"


def test_get_entity_reports_the_parent_field() -> None:
    repo, person_id = _repo_with_experimentalist()

    person = repo.get_entity(person_id)

    assert person is not None
    assert person.parent_field == "experimentalists"
