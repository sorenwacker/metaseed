"""A push refuses an Investigation, Study or Assay that has no title.

SEEK identifies these records by title, and a re-push finds what an earlier
push made by that title. An entity without one was sent as its tree label,
``New Study`` or ``New Assay``: every untitled dataset then landed on the same
SEEK Study, and the CropXR demo appeared in SEEK as "New Study" with
"New Assay (...)" beneath it.
"""

from __future__ import annotations

from tests.test_seek.test_sync import _FakeSeek

from metaseed import MetaseedClient
from metaseed.seek.sync import sync_dataset_to_seek
from metaseed.seek.values import title_of
from metaseed.specs.loader import SpecLoader


def _dataset(study: dict[str, str]) -> MetaseedClient:
    client = MetaseedClient("seek-ready-template", "3.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "My Investigation"},
        skip_validation=True,
    )
    made = client.create_entity("Study", study, parent_id=inv.id, skip_validation=True)
    client.create_entity(
        "Assay",
        {"identifier": "ASSAY1", "title": "Assay one"},
        parent_id=made.id,
        skip_validation=True,
    )
    return client


def test_an_untitled_study_stops_the_push_before_anything_is_created() -> None:
    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek, _dataset({"description": "no name at all"}), project_id="1"
    )

    assert seek.calls == [], "the push wrote to SEEK"
    (message,) = [m for _, m in result.errors]
    assert message.startswith("Study ") and "'title'" in message


def test_no_record_is_named_after_the_tree_label() -> None:
    seek = _FakeSeek()
    sync_dataset_to_seek(seek, _dataset({"description": "x"}), project_id="1")

    titles = [payload.get("title", "") for _, payload in seek.calls]
    assert not [t for t in titles if str(t).startswith("New ")]


def test_a_titled_dataset_pushes_under_its_titles() -> None:
    seek = _FakeSeek()
    result = sync_dataset_to_seek(
        seek, _dataset({"identifier": "STU1", "title": "Study one"}), project_id="1"
    )

    assert not result.errors
    assert [p["title"] for k, p in seek.calls if k == "study"] == ["Study one"]


def test_the_title_is_the_profiles_label_field() -> None:
    """A profile may label an entity by a field not called ``title``."""
    spec = SpecLoader().load_profile(version="3.0", profile="seek-ready-template")
    study = spec.entities["Study"].model_copy(deep=True)
    for f in study.fields:
        f.is_label = f.name == "description"

    assert title_of(study, {"title": "t", "description": "Labelled"}) == "Labelled"
    assert title_of(study, {"title": "t", "identifier": "STU1"}) == "STU1", (
        "without its label the record is named by its identifier"
    )
    assert title_of(study, {"title": "t"}) is None


def test_an_untitled_sample_stops_the_push_too() -> None:
    client = _dataset({"identifier": "STU1", "title": "Study one"})
    study = next(n for n in client.get_tree()[0].children)
    client.create_entity(
        "Source", {"organism": "x"}, parent_id=study.id, skip_validation=True
    )
    seek = _FakeSeek()
    result = sync_dataset_to_seek(seek, client, project_id="1")

    assert seek.calls == []
    assert [m for _, m in result.errors if m.startswith("Source ")]
