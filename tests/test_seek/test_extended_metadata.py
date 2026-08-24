"""Study and Assay field values are pushed into the installed Extended Metadata Types.

An entity names its type by title (``seek.extended_metadata``); a prefix group
(``seek.extended_metadata_groups``) sends flattened ``site_*`` fields into the
nested ``location`` type. See ``docs/architecture/seek-isa-compliance.md``.
"""

from __future__ import annotations

import copy
from typing import Any

from tests.test_seek.test_sync import _FakeSeek, _of_kind
from tests.test_seek.test_template_bound import _SPEC

from metaseed import MetaseedClient
from metaseed.seek.payloads import extended_metadata_pairs, isa_study_form
from metaseed.seek.sync import sync_dataset_to_seek


def _spec_with_metadata() -> dict[str, Any]:
    spec = copy.deepcopy(_SPEC)
    study = spec["entities"]["Study"]
    study["fields"] = [
        *study["fields"][:2],
        {"name": "study_start_date", "type": "string"},
        {"name": "site_latitude", "type": "string"},
        {"name": "site_country", "type": "string"},
        {"name": "not_in_seek", "type": "string"},
        *study["fields"][2:],
    ]
    study["seek"] = {
        "role": "Study",
        "extended_metadata": "CropXR phenotyping study",
        "extended_metadata_groups": {"site": "location"},
    }
    spec["entities"]["Assay"]["seek"] = {
        "role": "Assay",
        "extended_metadata": "CropXR phenotyping assay",
    }
    return spec


def _seek() -> _FakeSeek:
    seek = _FakeSeek()
    seek.emt_ids = {"CropXR phenotyping study": "19", "CropXR phenotyping assay": "22"}
    seek.emt_attributes = {
        "19": {"study_id": None, "study_start_date": None, "location": "18"},
        "18": {"latitude": None, "country": None},
        "22": {"trait": None},
    }
    return seek


def _dataset() -> MetaseedClient:
    c = MetaseedClient.from_spec(_spec_with_metadata())
    inv = c.create_entity(
        "Investigation", {"identifier": "I1", "title": "inv"}, skip_validation=True
    )
    study = c.create_entity(
        "Study",
        {
            "study_id": "S1",
            "title": "study",
            "study_start_date": "2026-03-01",
            "site_latitude": "51.98",
            "site_country": "Netherlands",
            "not_in_seek": "x",
        },
        parent_id=inv.id,
        skip_validation=True,
    )
    c.create_entity(
        "Assay",
        {"identifier": "A1", "title": "assay one", "trait": "height"},
        parent_id=study.id,
        skip_validation=True,
    )
    return c


def test_the_form_pairs_follow_seeks_permitted_keys() -> None:
    pairs = extended_metadata_pairs(
        "isa_study[study]",
        "19",
        {
            "study_id": "S1",
            "location": {"latitude": "51.98"},
            "tags": ["a", "b"],
            "empty": "",
        },
    )
    assert pairs == [
        (
            "isa_study[study][extended_metadata_attributes][extended_metadata_type_id]",
            "19",
        ),
        ("isa_study[study][extended_metadata_attributes][data][study_id]", "S1"),
        (
            "isa_study[study][extended_metadata_attributes][data][location][latitude]",
            "51.98",
        ),
        ("isa_study[study][extended_metadata_attributes][data][tags][]", "a"),
        ("isa_study[study][extended_metadata_attributes][data][tags][]", "b"),
    ]


def test_the_study_form_carries_the_metadata() -> None:
    pairs = isa_study_form(
        title="s",
        investigation_id="1",
        source_title="src",
        source_attributes=[],
        collection_title="col",
        collection_attributes=[],
        extended_metadata=("19", {"study_id": "S1"}),
    )
    assert (
        "isa_study[study][extended_metadata_attributes][data][study_id]",
        "S1",
    ) in pairs


def test_study_values_land_in_the_type_with_the_nested_group() -> None:
    seek = _seek()
    result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
    assert not result.errors, result.errors
    (study,) = _of_kind(seek, "study")
    type_id, data = study["extended_metadata"]
    assert type_id == "19"
    assert data == {
        "study_id": "S1",
        "study_start_date": "2026-03-01",
        "location": {"latitude": "51.98", "country": "Netherlands"},
    }


def test_a_field_the_type_lacks_is_reported_not_dropped_silently() -> None:
    seek = _seek()
    result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
    assert any("not_in_seek" in msg for _, msg in result.skipped), result.skipped
    # The record's own identity fields are its title, not metadata beside it.
    assert not any("identifier" in msg or "title" in msg for _, msg in result.skipped)


def test_assay_values_land_in_the_assay_type() -> None:
    seek = _seek()
    sync_dataset_to_seek(seek, _dataset(), project_id="1")
    (assay,) = _of_kind(seek, "assay")
    assert assay["extended_metadata"] == ("22", {"trait": "height"})


def test_a_missing_type_is_an_error_not_a_silent_drop() -> None:
    seek = _FakeSeek()  # no types installed
    result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
    assert any("CropXR phenotyping study" in msg for _, msg in result.errors)
