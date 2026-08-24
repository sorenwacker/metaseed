"""Profile entities derived from SEEK ISA Template definitions, column for column.

The gate for "the synced Sample Type is exactly the installed template": a
template file turned into a profile entity and rendered back by the same plan
the sync builds the type from must reproduce the template's attributes.
"""

from __future__ import annotations

import copy
from typing import Any

from tests.test_seek.test_sync import _FakeSeek, _of_kind

from metaseed import MetaseedClient
from metaseed.seek.definitions import (
    apply_isa_templates,
    entity_from_isa_template,
    field_from_template_attribute,
)
from metaseed.seek.provision import build_provisioning_plan
from metaseed.seek.sync import sync_dataset_to_seek
from metaseed.seek.templates import to_isa_template_json

# A template in the definitions repository's shape (an excerpt of
# ``observation_unit.json`` plus a data-file attribute and a vocabulary).
_TEMPLATE: dict[str, Any] = {
    "metadata": {
        "name": "CropXR phenotyping observation unit",
        "group": "CropXR phenotyping",
        "group_order": 1,
        "temporary_name": "1_cropxr_observation_unit",
        "version": "1.1.0",
        "organism": "any",
        "level": "study sample",
    },
    "data": [
        {
            "name": "Input",
            "description": "Existing study sources that are the input.",
            "dataType": "Registered Sample List",
            "required": True,
            "isaTag": "input",
        },
        {
            "name": "subject_id",
            "description": "Unique id of the observation unit.",
            "dataType": "String",
            "title": True,
            "required": True,
            "isaTag": "sample",
        },
        {
            "name": "collection_date",
            "description": "When it was collected.",
            "dataType": "ENA custom date",
            "isaTag": "parameter_value",
        },
        {
            "name": "growth_medium",
            "description": "Growth medium.",
            "dataType": "Controlled Vocabulary",
            "isaTag": "sample_characteristic",
            "CVList": ["soil", "hydroponic"],
            "allowCVFreeText": True,
        },
        {
            "name": "photo",
            "description": "Reference image.",
            "dataType": "Registered Data file",
            "isaTag": "sample_characteristic",
        },
    ],
}


def test_every_attribute_maps_to_a_field_keeping_the_exact_seek_type() -> None:
    fields = {f["name"]: f for f in entity_from_isa_template(_TEMPLATE)["fields"]}
    assert fields["Input"] == {
        "name": "Input",
        "type": "list",
        "items": "string",
        "required": True,
        "description": "Existing study sources that are the input.",
        "isa_tag": "input",
        "seek_attribute_type": "Registered Sample List",
    }
    assert fields["subject_id"]["is_label"] is True
    assert "seek_attribute_type" not in fields["subject_id"], "String is implied"
    assert fields["collection_date"]["seek_attribute_type"] == "ENA custom date"
    assert fields["growth_medium"]["constraints"] == {"enum": ["soil", "hydroponic"]}
    assert fields["growth_medium"]["seek_controlled_vocab"] == "growth_medium"
    assert fields["growth_medium"]["seek_cv_free_text"] is True
    assert fields["photo"] == {
        "name": "photo",
        "type": "uri",
        "description": "Reference image.",
        "isa_tag": "sample_characteristic",
        "seek_attribute_type": "Registered Data file",
    }


def test_an_unknown_seek_type_is_refused_not_guessed() -> None:
    import pytest

    with pytest.raises(ValueError, match="no profile mapping"):
        field_from_template_attribute({"name": "x", "dataType": "Registered Strain"})


def _profile_spec() -> dict[str, Any]:
    entity = entity_from_isa_template(_TEMPLATE)
    return {
        "name": "cropxr-derived",
        "version": "1.0",
        "root_entity": "Investigation",
        "entities": {
            "Investigation": {
                "fields": [
                    {"name": "identifier", "type": "string"},
                    {"name": "studies", "type": "list", "items": "Study"},
                ],
                "seek": {"role": "Investigation"},
            },
            "Study": {
                "fields": [
                    {"name": "study_id", "type": "string"},
                    {"name": "units", "type": "list", "items": "Unit"},
                ],
                "seek": {"role": "Study"},
            },
            "Unit": entity,
        },
    }


def test_the_derived_entity_renders_back_to_the_template_column_for_column() -> None:
    # The exactness gate: what the sync will build the type from is what the
    # definition says, attribute by attribute.
    profile = MetaseedClient.from_spec(_profile_spec()).facade.profile_spec
    rendered = {
        t["metadata"]["name"]: t for t in to_isa_template_json(profile)["data"]
    }[_TEMPLATE["metadata"]["name"]]
    assert rendered["metadata"]["level"] == "study sample"
    keys = (
        "name",
        "description",
        "dataType",
        "required",
        "isaTag",
        "title",
        "CVList",
        "allowCVFreeText",
    )

    def normalise(a: dict[str, Any]) -> dict[str, Any]:
        out = {k: a.get(k) for k in keys}
        out["required"] = bool(out["required"])
        return out

    assert [normalise(a) for a in rendered["data"]] == [
        normalise(a) for a in _TEMPLATE["data"]
    ]


def test_the_sync_binds_the_instance_vocabulary_and_the_template_attribute() -> None:
    client = MetaseedClient.from_spec(_profile_spec())
    inv = client.create_entity(
        "Investigation", {"identifier": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study", {"study_id": "S"}, parent_id=inv.id, skip_validation=True
    )
    client.create_entity(
        "Unit",
        {"subject_id": "OU-1", "growth_medium": "soil"},
        parent_id=study.id,
        skip_validation=True,
    )
    seek = _FakeSeek()
    seek.instance_cvs = {"growth_medium": "cv-77"}
    seek.template_attributes = {
        "template-for-CropXR phenotyping observation unit": {
            "subject_id": "901",
            "growth_medium": "902",
        }
    }
    result = sync_dataset_to_seek(seek, client, project_id="1")
    assert not result.errors, result.errors
    (study_call,) = _of_kind(seek, "study")
    by_title = {a["title"]: a for a in study_call["collection_attributes"]}
    assert by_title["growth_medium"]["sample_controlled_vocab_id"] == "cv-77"
    assert by_title["growth_medium"]["allow_cv_free_text"] is True
    assert by_title["growth_medium"]["template_attribute_id"] == "902"
    assert by_title["collection_date"]["attribute_type_title"] == "ENA custom date"


def test_a_missing_instance_vocabulary_is_an_error_naming_the_column() -> None:
    client = MetaseedClient.from_spec(_profile_spec())
    inv = client.create_entity(
        "Investigation", {"identifier": "I"}, skip_validation=True
    )
    client.create_entity(
        "Study", {"study_id": "S"}, parent_id=inv.id, skip_validation=True
    )
    result = sync_dataset_to_seek(_FakeSeek(), client, project_id="1")
    assert any("growth_medium" in msg for _, msg in result.errors), result.errors


def test_provisioning_does_not_copy_an_instance_bound_vocabulary() -> None:
    profile = MetaseedClient.from_spec(_profile_spec()).facade.profile_spec
    assert build_provisioning_plan(profile).cvs == ()


def test_apply_keeps_what_only_the_profile_knows_and_drops_dead_columns() -> None:
    document = _profile_spec()
    unit = document["entities"]["Unit"]
    unit["fields"] = [
        {
            "name": "Input",
            "type": "list",
            "items": "string",
            "isa_tag": "input",
            "reference": "Source",
        },
        {
            "name": "subject_id",
            "type": "string",
            "isa_tag": "sample",
            "ontology_term": "OBI:0000747",
        },
        {"name": "stale_column", "type": "string"},
    ]
    applied = apply_isa_templates(document, [copy.deepcopy(_TEMPLATE)])
    assert applied == {"Unit": ["stale_column"]}
    fields = {f["name"]: f for f in document["entities"]["Unit"]["fields"]}
    assert fields["Input"]["reference"] == "Source"
    assert fields["subject_id"]["ontology_term"] == "OBI:0000747"
    assert "stale_column" not in fields
    assert set(fields) == {a["name"] for a in _TEMPLATE["data"]}
    assert [f["name"] for f in fields.values() if f.get("is_label")] == ["subject_id"]


def test_a_registered_data_file_column_gets_the_file_registered_and_its_id() -> None:
    client = MetaseedClient.from_spec(_profile_spec())
    inv = client.create_entity(
        "Investigation", {"identifier": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study", {"study_id": "S"}, parent_id=inv.id, skip_validation=True
    )
    client.create_entity(
        "Unit",
        {"subject_id": "OU-1", "photo": "https://data.example.org/ou-1.jpg"},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity(
        "Unit",
        {"subject_id": "OU-2", "photo": "https://data.example.org/ou-1.jpg"},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity(
        "Unit",
        {"subject_id": "OU-3", "photo": "not a url"},
        parent_id=study.id,
        skip_validation=True,
    )
    seek = _FakeSeek()
    seek.instance_cvs = {"growth_medium": "cv-77"}
    result = sync_dataset_to_seek(seek, client, project_id="1")
    assert not result.errors, result.errors
    files = _of_kind(seek, "data_file")
    assert [f["url"] for f in files] == ["https://data.example.org/ou-1.jpg"], (
        "one URL, registered once"
    )
    samples = {s["data"]["subject_id"]: s["data"] for s in _of_kind(seek, "sample")}
    file_id = next(iter(result.data_files.values()))
    assert samples["OU-1"]["photo"] == file_id
    assert samples["OU-2"]["photo"] == file_id
    assert "photo" not in samples["OU-3"]
    assert any("OU-3" in n or "not a url" in msg for n, msg in result.notes)
