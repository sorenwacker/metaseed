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
    assert sample_call["data"]["name"] == "sample-a"


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
