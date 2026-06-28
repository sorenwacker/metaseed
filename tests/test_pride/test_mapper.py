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
    dataset = _dataset(build_dataset(_project(), _files()))

    species = dataset["species"]
    assert species == [{"name": "Erwinia carotovora", "ncbi_taxonomy_id": "554"}]


def test_instruments_and_modifications_carry_cv_accessions():
    dataset = _dataset(build_dataset(_project(), _files()))

    instrument = dataset["instruments"][0]
    assert instrument["cv_accession"] == "MS:1001742"
    assert instrument["cv_name"] == "LTQ Orbitrap Velos"

    mods = {m["name"]: m["cv_accession"] for m in dataset["modifications"]}
    assert mods["monohydroxylated residue"] == "MOD:00425"


def test_contacts_split_into_submitter_and_lab_head():
    dataset = _dataset(build_dataset(_project(), _files()))

    by_role = {c["role"]: c for c in dataset["contacts"]}
    assert by_role["submitter"]["name"] == "Laurent Gatto"
    assert by_role["submitter"]["orcid"] == "0000-0002-1520-2268"
    assert by_role["lab head"]["name"] == "Kathryn Lilley"
    # Empty orcid is dropped, not stored as a blank string.
    assert "orcid" not in by_role["lab head"]


def test_publications_are_mapped():
    dataset = _dataset(build_dataset(_project(), _files()))

    pub = dataset["publications"][0]
    assert pub["doi"] == "10.1016/j.bbapap.2013.04.032"
    assert pub["pubmed_id"] == "23692960"


def test_samples_are_synthesized_from_organisms():
    dataset = _dataset(build_dataset(_project(), _files()))

    sample = dataset["samples"][0]
    assert sample["species"] == "Erwinia carotovora"
    assert sample["ncbi_taxonomy_id"] == "554"
    assert sample["tissue"] == "whole organism"


def test_files_are_referenced_with_type_and_size():
    dataset = _dataset(build_dataset(_project(), _files()))

    files = {f["filename"]: f for f in dataset["files"]}
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
