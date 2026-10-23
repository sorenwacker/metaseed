"""An entity with the SOP role is registered in SEEK as an SOP (#359).

SEEK's role list had no SOP, so a profile could not upload its protocols as
SOPs: an SOP entity was reported as having no SEEK role and left behind.
"""

from __future__ import annotations

from tests.test_seek.test_sync import _FakeSeek, _of_kind

from metaseed import MetaseedClient
from metaseed.seek.payloads import sop_payload
from metaseed.seek.sync import sync_dataset_to_seek

_URL = "https://protocols.example.org/sop/leaf-nitrogen-v2.pdf"


def test_an_sop_is_a_remote_content_blob_linked_to_its_assays() -> None:
    body = sop_payload(
        title="Leaf nitrogen",
        project_id="7",
        url=_URL,
        original_filename="v2.pdf",
        assay_ids=["3"],
    )

    data = body["data"]
    assert data["type"] == "sops"
    assert data["attributes"]["content_blobs"] == [
        {"url": _URL, "original_filename": "v2.pdf"}
    ]
    assert data["relationships"]["projects"]["data"] == [
        {"type": "projects", "id": "7"}
    ]
    assert data["relationships"]["assays"]["data"] == [{"type": "assays", "id": "3"}]


def _dataset(sop: dict) -> MetaseedClient:
    client = MetaseedClient("seek-ready-template", "4.0")
    inv = client.create_entity("Investigation", {"title": "Investigation one"})
    study = client.create_entity(
        "Study", {"title": "Study one"}, parent_id=inv.id, skip_validation=True
    )
    assay = client.create_entity(
        "Assay",
        {"title": "Leaf nitrogen content"},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity("SOP", sop, parent_id=assay.id, skip_validation=True)
    return client


def test_an_sop_under_an_assay_is_registered_and_linked_to_it() -> None:
    seek = _FakeSeek()

    result = sync_dataset_to_seek(
        seek, _dataset({"title": "Leaf nitrogen SOP", "url": _URL}), project_id="1"
    )

    sops = _of_kind(seek, "sop")
    assert len(sops) == 1, result.skipped
    assay_id = next(iter(result.assays.values()))
    assert sops[0]["url"] == _URL
    assert sops[0]["title"] == "Leaf nitrogen SOP"
    assert sops[0]["assay_ids"] == [assay_id]
    assert list(result.sops.values()), "the SOP is not in the result"


def test_an_sop_without_a_location_is_reported_not_registered() -> None:
    seek = _FakeSeek()

    result = sync_dataset_to_seek(
        seek, _dataset({"title": "Unlinked SOP"}), project_id="1"
    )

    assert not _of_kind(seek, "sop")
    assert any("location" in reason for _, reason in result.skipped), result.skipped


def test_an_unreachable_location_is_named_in_the_error() -> None:
    """SEEK checks that an SOP's link resolves and answers only "bad upload"."""

    class _Unreachable(_FakeSeek):
        def create_sop(self, **kwargs):
            raise RuntimeError(
                "SEEK rejected POST /sops (400): {'error': 'bad upload'}"
            )

    seek = _Unreachable()

    result = sync_dataset_to_seek(
        seek, _dataset({"title": "Leaf nitrogen SOP", "url": _URL}), project_id="1"
    )

    assert any(_URL in reason and "reach" in reason for _, reason in result.errors), (
        result.errors
    )


def test_a_second_push_reuses_the_registered_sop() -> None:
    seek = _FakeSeek(existing_sops={"Leaf nitrogen SOP": "42"})

    result = sync_dataset_to_seek(
        seek, _dataset({"title": "Leaf nitrogen SOP", "url": _URL}), project_id="1"
    )

    assert not _of_kind(seek, "sop")
    assert "42" in result.sops.values()
    assert "42" in result.reused.values()
