"""Contract tests for AsyncSpecDraftStore via the in-memory default adapter."""

import pytest

from metaseed.repositories import MemorySpecDraftStore, SpecDraftData


@pytest.fixture
def store() -> MemorySpecDraftStore:
    # Fixed clock so ordering/timestamps are deterministic.
    counter = {"n": 0}

    def now() -> str:
        counter["n"] += 1
        return f"2026-01-01T00:00:0{counter['n']}Z"

    return MemorySpecDraftStore(now=now)


async def test_create_assigns_id_and_persists(store: MemorySpecDraftStore) -> None:
    draft = await store.create("MyProfile", "0.1", {"spec": {"name": "MyProfile"}})
    assert draft.id
    assert isinstance(draft, SpecDraftData)
    loaded = await store.load(draft.id)
    assert loaded.name == "MyProfile"
    assert loaded.spec_data == {"spec": {"name": "MyProfile"}}


async def test_load_missing_raises_keyerror(store: MemorySpecDraftStore) -> None:
    with pytest.raises(KeyError):
        await store.load("nope")


async def test_save_updates_state(store: MemorySpecDraftStore) -> None:
    draft = await store.create("P", "0.1", {"a": 1})
    await store.save(draft.id, "P2", "0.2", {"a": 2})
    loaded = await store.load(draft.id)
    assert loaded.name == "P2"
    assert loaded.version == "0.2"
    assert loaded.spec_data == {"a": 2}


async def test_save_missing_raises_keyerror(store: MemorySpecDraftStore) -> None:
    with pytest.raises(KeyError):
        await store.save("nope", "P", "0.1", {})


async def test_list_is_most_recent_first(store: MemorySpecDraftStore) -> None:
    a = await store.create("A", "0.1", {})
    b = await store.create("B", "0.1", {})
    listed = await store.list()
    assert [d.id for d in listed] == [b.id, a.id]
    assert [d.name for d in listed] == ["B", "A"]


async def test_delete_and_exists(store: MemorySpecDraftStore) -> None:
    draft = await store.create("P", "0.1", {})
    assert await store.exists(draft.id) is True
    assert await store.delete(draft.id) is True
    assert await store.exists(draft.id) is False
    assert await store.delete(draft.id) is False
