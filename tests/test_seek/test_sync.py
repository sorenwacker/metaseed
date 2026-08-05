"""Tests for the SEEK data pusher (dataset -> Investigations/Studies/Samples)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metaseed import MetaseedClient
from metaseed.seek.sync import sync_dataset_to_seek


@dataclass
class _FakeSeek:
    """Records ISA/sample creates, handing out incrementing ids per kind."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _n: int = 0

    def _next(self) -> str:
        self._n += 1
        return str(self._n)

    def create_investigation(
        self, *, title: str, project_id: str, description: str | None = None
    ) -> str:
        self.calls.append(("investigation", {"title": title}))
        return self._next()

    def create_study(
        self, *, title: str, investigation_id: str, description: str | None = None
    ) -> str:
        self.calls.append(
            ("study", {"title": title, "investigation_id": investigation_id})
        )
        return self._next()

    def create_assay(self, *, title: str, study_id: str) -> str:
        self.calls.append(("assay", {"title": title, "study_id": study_id}))
        return self._next()

    def create_sample(
        self, *, sample_type_id: str, project_id: str, data: dict[str, Any]
    ) -> str:
        self.calls.append(("sample", {"sample_type_id": sample_type_id, "data": data}))
        return self._next()


def _dataset() -> MetaseedClient:
    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "My Investigation"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU1", "title": "Study one"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample", {"name": "sample-a"}, parent_id=study.id, skip_validation=True
    )
    return client


def test_sync_creates_isa_hierarchy_and_threads_ids():
    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek,  # type: ignore[arg-type]
        _dataset(),
        project_id="1",
        sample_type_ids={"Sample": "st-9"},
    )

    kinds = [c[0] for c in seek.calls]
    assert kinds == ["investigation", "study", "sample"]
    assert not result.errors and not result.skipped
    assert len(result.investigations) == 1
    assert len(result.studies) == 1
    assert len(result.samples) == 1
    assert result.created_count == 3

    # study links the created investigation; sample uses the mapped sample type.
    inv_id = next(iter(result.investigations.values()))
    study_call = next(c for k, c in seek.calls if k == "study")
    assert study_call["investigation_id"] == inv_id
    sample_call = next(c for k, c in seek.calls if k == "sample")
    assert sample_call["sample_type_id"] == "st-9"
    # a core identity field (name) is routed onto the Sample Type's Title attribute
    assert sample_call["data"]["Title"] == "sample-a"


def test_sample_data_routes_core_fields_and_keeps_scalar_lists():
    from metaseed.seek.sync import _sample_data

    data = _sample_data(
        {
            "_node_id": "x",  # metadata key dropped
            "unique_id": "s1",  # core identity -> Title
            "description": "d",  # core -> Description
            "empty": "",  # empty dropped
            "organism": "human",  # non-core field kept under its own name
            "tags": ["a", "b"],  # scalar list kept (CV list)
            "nested": {"k": "v"},  # non-scalar dropped
            "mixed": ["a", {"k": 1}],  # list with a dict dropped
        }
    )
    assert data == {
        "Title": "s1",
        "Description": "d",
        "organism": "human",
        "tags": ["a", "b"],
    }


def test_sync_consumes_an_in_memory_spec_dataset():
    # A dataset built via ``from_spec`` (e.g. one produced by the SEEK importer)
    # has no installed profile file. sync must read its in-memory ProfileSpec
    # rather than calling SpecLoader unconditionally, which would raise
    # SpecLoadError for the derived "seek-imported" profile.
    spec = {
        "name": "seek-imported",
        "version": "1.0",
        "root_entity": "Investigation",
        "entities": {
            "Investigation": {
                "fields": [
                    {"name": "identifier", "type": "string", "required": True},
                    {"name": "title", "type": "string"},
                    {"name": "studies", "type": "list", "items": "Study"},
                ],
                "seek": {"role": "Investigation"},
            },
            "Study": {
                "fields": [{"name": "identifier", "type": "string", "required": True}],
                "seek": {"role": "Study"},
            },
        },
    }
    dataset = MetaseedClient.from_spec(spec)
    inv = dataset.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "Imported"},
        skip_validation=True,
    )
    dataset.create_entity(
        "Study", {"identifier": "STU1"}, parent_id=inv.id, skip_validation=True
    )

    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek,  # type: ignore[arg-type]
        dataset,
        project_id="1",
        sample_type_ids={},
    )
    assert [c[0] for c in seek.calls] == ["investigation", "study"]
    assert not result.errors


def test_sample_data_core_collapse_is_priority_ordered_not_dict_ordered():
    from metaseed.seek.sync import _sample_data

    # ``title`` appears first in dict order but ``identifier`` outranks it, so
    # Title takes the identifier value regardless of insertion order.
    assert _sample_data({"title": "label", "identifier": "ID-1"})["Title"] == "ID-1"
    assert _sample_data({"identifier": "ID-1", "title": "label"})["Title"] == "ID-1"
    # unique_id outranks identifier.
    assert _sample_data({"identifier": "ID-1", "unique_id": "U-1"})["Title"] == "U-1"


def test_sync_skips_sample_without_provisioned_type():
    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek,  # type: ignore[arg-type]
        _dataset(),
        project_id="1",
        sample_type_ids={},  # no Sample Type provisioned
    )

    assert [c[0] for c in seek.calls] == ["investigation", "study"]  # no sample
    assert len(result.skipped) == 1
    _node_id, reason = result.skipped[0]
    assert "Sample Type" in reason


def test_a_sample_whose_label_field_is_not_a_core_name_still_gets_a_title():
    """SEEK requires a Sample's Title; without it the POST is a 422.

    ``_sample_data`` derives Title only from ``identifier``/``unique_id``/
    ``name``/``title``. A profile whose Sample-role entity identifies itself by
    another field -- cropxr's ``Source`` uses ``Source Name`` -- produced a
    Sample with a blank Title, and every such sample was rejected. The Title now
    falls back to the node's label, which is never blank.
    """
    from metaseed.seek.sync import sync_dataset_to_seek

    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "INV1", "title": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    # A sample carrying only a field SEEK's core mapping does not recognise.
    client.create_entity(
        "Sample", {"source_name": "S-1"}, parent_id=study.id, skip_validation=True
    )

    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek, client, project_id="1", sample_type_ids={"Sample": "st1"}
    )

    assert not result.errors, result.errors
    sample_calls = [c for kind, c in seek.calls if kind == "sample"]
    assert sample_calls, "the sample was not created"
    assert sample_calls[0]["data"].get("Title"), "Title must not be blank"


def test_a_plain_list_field_is_joined_for_seek_text_attribute():
    """A list field without an enum is provisioned as a scalar SEEK Text
    attribute, so its array value must be sent as a string. Sending the raw
    array made SEEK read the attribute as blank and reject the sample with
    ``Input: is required``, even though the value was present."""
    from metaseed.seek.sync import _sample_data

    # "Input" is a plain list (Text attribute); "tags" is an enum list (CV List).
    data = _sample_data(
        {"Input": ["SRC-1", "SRC-2"], "tags": ["a", "b"]},
        text_list_fields=frozenset({"Input"}),
    )

    assert isinstance(data["Input"], str), data["Input"]
    assert "SRC-1" in data["Input"] and "SRC-2" in data["Input"]
    assert data["tags"] == ["a", "b"]  # enum list stays an array


def test_sample_with_a_required_list_field_syncs():
    """End to end: a Sample carrying a plain-list field is created, not 422'd."""
    from metaseed.seek.sync import sync_dataset_to_seek

    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "I", "title": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "S", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    # Sample has no list field in ISA, so force one through a value; the point is
    # the join happens for list-valued data regardless of the profile shape.
    client.create_entity(
        "Sample",
        {"name": "smp", "sources": ["A", "B"]},
        parent_id=study.id,
        skip_validation=True,
    )

    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek, client, project_id="1", sample_type_ids={"Sample": "st"}
    )
    assert not result.errors, result.errors
