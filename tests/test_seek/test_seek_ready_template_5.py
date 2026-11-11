"""seek-ready-template 5.0 declares every column SEEK requires.

4.0 left the sample types' structural columns to the sync, which added a
``Title``, an ``Input`` and a ``Protocol`` column to every Source, Sample and
AssayMaterial type on push. Nobody reading the profile, a person or an
assistant cloning it, could see that those columns exist or that they may not
be changed. 5.0 declares them as fields, tags each level's name field as its ISA
title column, and links the chain through ``Input`` as SEEK does.
"""

from __future__ import annotations

import pytest

from metaseed import MetaseedClient
from metaseed.seek.isa_types import entity_level, sample_type_attribute_plans
from metaseed.specs.loader import SpecLoader

REQUIRED_BY_SEEK = "Required by SEEK"

# entity -> {field: (isa_tag or None, reference or None)}
_SEEK_FIELDS: dict[str, dict[str, tuple[str | None, str | None]]] = {
    "Investigation": {"title": (None, None), "description": (None, None)},
    "Study": {"title": (None, None), "description": (None, None)},
    "Assay": {
        "title": (None, None),
        "description": (None, None),
        "assay_class": (None, None),
        "assay_type": (None, None),
    },
    "SOP": {"title": (None, None), "url": (None, None)},
    "Source": {"source_name": ("source", None)},
    "Sample": {
        "sample_name": ("sample", None),
        "Input": ("input", "Source"),
        "Protocol": ("protocol", None),
    },
    "AssayMaterial": {
        "material_name": ("other_material", None),
        "Input": ("input", "Sample"),
        "Protocol": ("protocol", None),
    },
}

_LEVELS = {
    "Source": "source",
    "Sample": "sample_collection",
    "AssayMaterial": "material",
}


def _profile():
    return SpecLoader().load_profile("5.0", "seek-ready-template")


def _field(entity: str, name: str):
    fields = {f.name: f for f in _profile().entities[entity].fields}
    assert name in fields, f"{entity} has no {name}"
    return fields[name]


@pytest.mark.parametrize(
    ("entity", "name"),
    [(entity, name) for entity, fields in _SEEK_FIELDS.items() for name in fields],
)
def test_every_column_seek_requires_is_declared_and_marked(
    entity: str, name: str
) -> None:
    field = _field(entity, name)
    tag, reference = _SEEK_FIELDS[entity][name]
    assert field.isa_tag == tag
    assert field.reference == reference
    assert REQUIRED_BY_SEEK in (field.description or "")


@pytest.mark.parametrize("entity", ["Sample", "AssayMaterial"])
def test_input_is_a_registered_sample_list(entity: str) -> None:
    field = _field(entity, "Input")
    assert field.type == "list"
    assert field.seek_attribute_type == "Registered Sample List"
    assert field.required


@pytest.mark.parametrize(("entity", "level"), _LEVELS.items())
def test_the_sync_synthesizes_no_column(entity: str, level: str) -> None:
    """Every column of the sample type comes from a declared field."""
    spec = _profile().entities[entity]
    assert entity_level(spec) is not None
    plans = sample_type_attribute_plans(spec, level=level, linked=level != "source")
    assert all(plan.field_name is not None for plan in plans)
    assert sum(plan.is_title for plan in plans) == 1


def test_samples_sit_under_the_study_and_materials_under_their_assay() -> None:
    entities = _profile().entities
    study = {f.name: f.items for f in entities["Study"].fields if f.items}
    assay = {f.name: f.items for f in entities["Assay"].fields if f.items}
    assert study == {"sources": "Source", "samples": "Sample", "assays": "Assay"}
    assert assay == {"sops": "SOP", "assay_materials": "AssayMaterial"}
    assert "assay" not in {f.name for f in entities["AssayMaterial"].fields}


def test_one_material_can_come_from_several_samples() -> None:
    client = MetaseedClient("seek-ready-template", "5.0")
    inv = client.create_entity(
        "Investigation", {"title": "Reanalysis", "description": "x"}
    )
    study = client.create_entity(
        "Study", {"title": "Heat", "description": "x"}, parent_id=inv.id
    )
    for accession in ("PRJEB1111", "PRJEB2222"):
        client.create_entity("Source", {"source_name": accession}, parent_id=study.id)
        client.create_entity(
            "Sample",
            {
                "sample_name": f"{accession}-reads",
                "Input": [accession],
                "Protocol": "download",
            },
            parent_id=study.id,
        )
    assay = client.create_entity(
        "Assay",
        {
            "title": "Combined RNA-seq analysis",
            "description": "x",
            "assay_class": "MODEL",
            "assay_type": "http://jermontology.org/ontology/JERMOntology#Model_type",
        },
        parent_id=study.id,
    )
    client.create_entity(
        "AssayMaterial",
        {
            "material_name": "combined-counts",
            "Input": ["PRJEB1111-reads", "PRJEB2222-reads"],
            "Protocol": "DESeq2",
        },
        parent_id=assay.id,
    )
    result = client.validate()
    assert result.valid, [(i.field, i.message) for i in result.issues]


def test_a_material_with_two_inputs_is_linked_to_both() -> None:
    """The sync joined a list ``Input`` into one text value before resolving it,
    so two sample names became one title nothing matched, and even resolved it
    linked only the first input. Verified against a live SEEK, where the
    material was left unplaced."""
    from tests.test_seek.test_sync import _FakeSeek, _of_kind

    from metaseed.seek.sync import sync_dataset_to_seek

    client = MetaseedClient("seek-ready-template", "5.0")
    inv = client.create_entity(
        "Investigation", {"title": "Reanalysis", "description": "x"}
    )
    study = client.create_entity(
        "Study", {"title": "Heat", "description": "x"}, parent_id=inv.id
    )
    for name in ("a", "b"):
        client.create_entity(
            "Source", {"source_name": f"src-{name}"}, parent_id=study.id
        )
        client.create_entity(
            "Sample",
            {"sample_name": f"smp-{name}", "Input": [f"src-{name}"], "Protocol": "p"},
            parent_id=study.id,
        )
    assay = client.create_entity(
        "Assay",
        {
            "title": "Combined",
            "description": "x",
            "assay_class": "EXP",
            "assay_type": "http://jermontology.org/ontology/JERMOntology#Experimental_assay_type",
        },
        parent_id=study.id,
    )
    client.create_entity(
        "AssayMaterial",
        {"material_name": "combined", "Input": ["smp-a", "smp-b"], "Protocol": "p"},
        parent_id=assay.id,
    )

    seek = _FakeSeek()
    result = sync_dataset_to_seek(seek, client, project_id="1")
    assert not result.unlinked, result.unlinked
    samples = {
        s["data"]["material_name" if "material_name" in s["data"] else "sample_name"]
        if ("material_name" in s["data"] or "sample_name" in s["data"])
        else None: s
        for s in _of_kind(seek, "sample")
    }
    material = samples["combined"]["data"]
    inputs = [v for k, v in material.items() if k.startswith("Input")]
    assert len(inputs) == 1 and len(inputs[0]) == 2, material
