"""Tests for the PRIDE -> pride-profile mapper (pure, no network)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed.pride.mapper import build_dataset

FIXTURES = Path(__file__).parent / "fixtures"


def _project() -> dict:
    return json.loads((FIXTURES / "project.json").read_text())


def _files() -> list[dict]:
    return json.loads((FIXTURES / "files.json").read_text())


def _entities(client) -> list[dict]:
    return client.serialize()["entities"]


def _by_type(client, entity_type: str) -> list[dict]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def _dataset(client) -> dict:
    return _by_type(client, "Dataset")[0]


def test_build_dataset_creates_one_dataset_root():
    client = build_dataset(_project(), _files())

    datasets = _by_type(client, "Dataset")
    assert len(datasets) == 1
    assert datasets[0]["accession"] == "PXD000001"
    assert datasets[0]["identifier"] == "PXD000001"


def test_core_project_fields_are_mapped():
    dataset = _dataset(build_dataset(_project(), _files()))

    assert dataset["title"].startswith("TMT spikes")
    assert dataset["submission_type"] == "COMPLETE"
    assert dataset["announcement_date"] == "2012-03-07"
    assert dataset["keywords"] == ["Spikes", "Tmt", "Eriwinia"]
    assert "Erwinia" in dataset["description"]


def test_species_carry_numeric_taxonomy_ids():
    client = build_dataset(_project(), _files())

    species = [
        {k: v for k, v in e.items() if not k.startswith("_")}
        for e in _by_type(client, "Species")
    ]
    assert species == [{"name": "Erwinia carotovora", "ncbi_taxonomy_id": "554"}]


def test_instruments_and_modifications_carry_cv_accessions():
    client = build_dataset(_project(), _files())

    instrument = _by_type(client, "Instrument")[0]
    assert instrument["cv_accession"] == "MS:1001742"
    assert instrument["cv_name"] == "LTQ Orbitrap Velos"

    mods = {m["name"]: m["cv_accession"] for m in _by_type(client, "Modification")}
    assert mods["monohydroxylated residue"] == "MOD:00425"


def test_contacts_split_into_submitter_and_lab_head():
    client = build_dataset(_project(), _files())

    by_role = {c["role"]: c for c in _by_type(client, "Contact")}
    assert by_role["submitter"]["name"] == "Alex Rivera"
    assert by_role["submitter"]["orcid"] == "0000-0001-2345-6789"
    assert by_role["lab head"]["name"] == "Jordan Blake"
    # Empty orcid is dropped, not stored as a blank string.
    assert "orcid" not in by_role["lab head"]


def test_publications_are_mapped():
    client = build_dataset(_project(), _files())

    pub = _by_type(client, "Publication")[0]
    assert pub["doi"] == "10.1016/j.bbapap.2013.04.032"
    assert pub["pubmed_id"] == "23692960"


def test_samples_are_synthesized_from_organisms():
    client = build_dataset(_project(), _files())

    sample = _by_type(client, "Sample")[0]
    assert sample["species"] == "Erwinia carotovora"
    assert sample["ncbi_taxonomy_id"] == "554"
    assert sample["tissue"] == "whole organism"


def test_files_are_referenced_with_type_and_size():
    client = build_dataset(_project(), _files())

    files = {f["filename"]: f for f in _by_type(client, "DataFile")}
    raw = files["TMT_Erwinia_1uLSike_Top10HCD_isol2_45stepped_60min_01.raw"]
    assert raw["file_type"] == "RAW"
    assert raw["file_format"] == "raw"
    assert raw["file_size"] == 243031280
    # Empty checksum dropped; a valid 32-hex checksum is kept.
    assert "checksum" not in raw
    mgf = files["PRIDE_Exp_Complete_Ac_22134.pride.mgf.gz"]
    assert mgf["file_type"] == "PEAK"
    assert mgf["file_format"] == "mgf"
    assert mgf["checksum"] == "098f6bcd4621d373cade4e832627b4f6"


def test_empty_project_yields_empty_dataset():
    client = build_dataset({}, [])
    assert client.serialize()["entities"] == []


# --- everything the API offers, as a navigable tree -------------------------


def test_experiment_types_are_not_dropped():
    """The project record carries them and the profile has a field for them, but
    the mapper never populated it — so an import lost the experiment type."""
    dataset = _dataset(build_dataset(_project(), _files()))

    assert dataset.get("experiment_types"), "experimentTypes were discarded"


def test_the_doi_and_licence_are_kept():
    """A DOI is the record's persistent identifier and a licence decides what a
    reuser may do; dropping either loses the two most reusable facts."""
    dataset = _dataset(build_dataset(_project(), _files()))

    assert dataset.get("doi")
    assert dataset.get("license")


def test_the_import_is_a_tree_not_a_single_node():
    """Nine entity types exist in the profile; an import that produces one node
    is indistinguishable from a failed import in the UI."""
    client = build_dataset(_project(), _files())

    roots = client.get_tree()
    assert len(roots) == 1, "one Dataset at the root"
    assert roots[0].children, "the Dataset has no children — nothing is navigable"


def test_each_record_becomes_its_own_entity():
    client = build_dataset(_project(), _files())

    assert [e["name"] for e in _by_type(client, "Species")] == ["Erwinia carotovora"]
    assert [e["name"] for e in _by_type(client, "Instrument")] == ["LTQ Orbitrap Velos"]
    assert len(_by_type(client, "Modification")) == 2
    assert len(_by_type(client, "Contact")) == 2
    assert len(_by_type(client, "Publication")) == 1
    assert len(_by_type(client, "Sample")) == 1
    assert len(_by_type(client, "DataFile")) == 3


def test_every_child_hangs_off_the_dataset():
    """A child parented elsewhere would be unreachable from the root."""
    client = build_dataset(_project(), _files())

    root = client.get_tree()[0]
    child_types = sorted({child.entity_type for child in root.children})
    assert child_types == [
        "Contact",
        "DataFile",
        "Instrument",
        "Modification",
        "Publication",
        "Sample",
        "Species",
    ]
