"""seek-ready-template 4.0 carries SEEK's own record fields (#359).

SEEK's Investigation, Study and Assay have no identifier attribute
(``investigationPost``, ``studyPost``, ``assayPost``), and an Assay requires an
``assay_class`` and an ``assay_type``. 3.0 required an identifier SEEK could not
hold, gave the Assay neither class nor type, and kept ISA-Tab fields such as
``study_design_type`` without saying that SEEK has no attribute for them.
"""

from __future__ import annotations

import pytest
from tests.test_seek.test_sync import _FakeSeek, _of_kind

from metaseed import MetaseedClient
from metaseed.seek.payloads import ASSAY_CLASS_IDS, DEFAULT_ASSAY_TYPE_URI
from metaseed.seek.preview import build_model_preview
from metaseed.seek.sync import sync_dataset_to_seek
from metaseed.specs.loader import SpecLoader

_MODELLING = "http://jermontology.org/ontology/JERMOntology#Model_type"


def _profile():
    return SpecLoader().load_profile("4.0", "seek-ready-template")


@pytest.mark.parametrize("entity", ["Investigation", "Study", "Assay"])
def test_the_title_identifies_the_record(entity) -> None:
    fields = {f.name: f for f in _profile().entities[entity].fields}

    assert "identifier" not in fields, f"SEEK's {entity} has no identifier attribute"
    title = fields["title"]
    assert title.required and title.is_identifier and title.is_label


def test_an_assay_carries_seeks_required_class_and_type() -> None:
    fields = {f.name: f for f in _profile().entities["Assay"].fields}

    assert fields["assay_class"].required
    assert fields["assay_class"].constraints.enum == ["EXP", "MODEL"]
    assert fields["assay_type"].required


def _dataset(assay: dict) -> MetaseedClient:
    client = MetaseedClient("seek-ready-template", "4.0")
    inv = client.create_entity("Investigation", {"title": "Investigation one"})
    study = client.create_entity(
        "Study", {"title": "Study one"}, parent_id=inv.id, skip_validation=True
    )
    client.create_entity("Assay", assay, parent_id=study.id, skip_validation=True)
    source = client.create_entity(
        "Source", {"source_name": "source-1"}, parent_id=study.id, skip_validation=True
    )
    sample = client.create_entity(
        "Sample", {"sample_name": "sample-1"}, parent_id=source.id, skip_validation=True
    )
    client.create_entity(
        "AssayMaterial",
        {"material_name": "material-1", "assay": assay["title"]},
        parent_id=sample.id,
        skip_validation=True,
    )
    return client


def test_the_sync_sends_the_assays_own_class_and_type() -> None:
    seek = _FakeSeek()
    assay = {"title": "Growth model", "assay_class": "MODEL", "assay_type": _MODELLING}

    sync_dataset_to_seek(seek, _dataset(assay), project_id="1")

    created = [
        a for a in _of_kind(seek, "assay") if a["title"].startswith("Growth model")
    ]
    assert created, "the assay was not created"
    assert created[0]["assay_class_id"] == ASSAY_CLASS_IDS["MODEL"]
    assert created[0]["assay_type_uri"] == _MODELLING


def test_an_assay_without_them_is_experimental_of_the_default_type() -> None:
    seek = _FakeSeek()

    sync_dataset_to_seek(seek, _dataset({"title": "Leaf profiling"}), project_id="1")

    created = [
        a for a in _of_kind(seek, "assay") if a["title"].startswith("Leaf profiling")
    ]
    assert created[0]["assay_class_id"] == ASSAY_CLASS_IDS["EXP"]
    assert created[0]["assay_type_uri"] in (None, DEFAULT_ASSAY_TYPE_URI)


def test_isa_only_fields_are_not_extended_metadata_in_the_preview() -> None:
    profile = _profile()
    isa_only = {
        (name, f.name)
        for name, entity in profile.entities.items()
        for f in entity.fields
        if f.seek_isa_only
    }

    preview = build_model_preview(profile)

    shown = {
        (record.entity_type, a.name)
        for record in preview.extended_metadata
        for a in record.attributes
    }
    assert isa_only, "4.0 marks its ISA-only fields"
    assert not isa_only & shown, sorted(isa_only & shown)
