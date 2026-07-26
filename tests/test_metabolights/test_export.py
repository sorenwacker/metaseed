"""Tests for the MetaboLights exporter (ISA-Tab + MAF)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed import MetaseedClient
from metaseed.metabolights import to_metabolights
from metaseed.metabolights.export import _MAF_HEADER
from metaseed.metabolights.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "study.json"


def _client():
    return build_dataset(json.loads(FIXTURE.read_text()))


def test_to_metabolights_includes_isatab_and_a_maf():
    docs = to_metabolights(_client())
    assert "i_Investigation.txt" in docs

    maf = [n for n in docs if "maf" in n.lower() or n.startswith("m_")]
    assert maf, f"no MAF document in {list(docs)}"
    assert "metabolite_identification" in docs[maf[0]]  # standard MAF header


# --- MAF population --------------------------------------------------------


def _client_with_metabolites(metabolites: list[dict]) -> MetaseedClient:
    """A metabolights dataset with one assay carrying the given metabolites."""
    client = MetaseedClient("metabolights", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "MTBLS1", "title": "t", "description": "d"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "s1", "title": "st", "description": "d"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Assay",
        {
            "identifier": "a1",
            "filename": "a_1.txt",
            "technology_type": "mass spectrometry",
            "measurement_type": "metabolite profiling",
            "samples": ["S1"],
            "metabolite_assignment_file": "m_a1_v2_maf.tsv",
            "metabolites": metabolites,
        },
        parent_id=study.id,
        skip_validation=True,
    )
    return client


def _maf(docs: dict[str, str]) -> list[list[str]]:
    name = next(n for n in docs if n.startswith("m_"))
    return [line.split("\t") for line in docs[name].splitlines()]


def test_maf_has_one_row_per_metabolite():
    docs = to_metabolights(
        _client_with_metabolites(
            [
                {
                    "metabolite_identification": "glucose",
                    "database_identifier": "CHEBI:17234",
                    "chemical_formula": "C6H12O6",
                    "inchi": "InChI=1S/C6H12O6",
                    "mass_to_charge": 180.06,
                    "charge": 1,
                    "reliability": "1",
                },
                {"metabolite_identification": "alanine", "chemical_formula": "C3H7NO2"},
            ]
        )
    )
    rows = _maf(docs)
    assert rows[0] == list(_MAF_HEADER)  # header
    assert len(rows) == 3  # header + 2 metabolites
    assert all(len(r) == len(_MAF_HEADER) for r in rows)  # rectangular


def test_maf_maps_metabolite_fields_to_columns():
    docs = to_metabolights(
        _client_with_metabolites(
            [
                {
                    "metabolite_identification": "glucose",
                    "database_identifier": "CHEBI:17234",
                    "chemical_formula": "C6H12O6",
                    "mass_to_charge": 180.06,
                }
            ]
        )
    )
    header, row = _maf(docs)[0], _maf(docs)[1]
    cell = dict(zip(header, row, strict=True))
    assert cell["metabolite_identification"] == "glucose"
    assert cell["database_identifier"] == "CHEBI:17234"
    assert cell["chemical_formula"] == "C6H12O6"
    assert cell["mass_to_charge"] == "180.06"
    # A column the profile does not model stays empty.
    assert cell["search_engine"] == ""


def test_maf_absent_field_renders_empty():
    docs = to_metabolights(
        _client_with_metabolites([{"metabolite_identification": "alanine"}])
    )
    header, row = _maf(docs)[0], _maf(docs)[1]
    cell = dict(zip(header, row, strict=True))
    assert cell["metabolite_identification"] == "alanine"
    assert cell["database_identifier"] == ""  # not provided
    assert cell["inchi"] == ""


def test_maf_without_metabolites_is_header_only():
    # Back-compat: an assay with no metabolites still yields a valid MAF header.
    docs = to_metabolights(_client_with_metabolites([]))
    rows = _maf(docs)
    assert rows == [list(_MAF_HEADER)]


# --- sample characteristics survive the study table ------------------------


def _client_with_sample(sample_fields: dict) -> MetaseedClient:
    """A metabolights dataset with a single study and one sample."""
    client = MetaseedClient("metabolights", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "MTBLS1", "title": "t", "description": "d"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "S1", "title": "st"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample", sample_fields, parent_id=study.id, skip_validation=True
    )
    return client


def _study_table(docs: dict[str, str]) -> str:
    return docs[next(n for n in docs if n.startswith("s_"))]


def test_sample_organism_is_emitted_as_a_characteristic_column():
    """The required ``organism`` must reach the study table, not be dropped.

    Before this the writer emitted only Source Name / Sample Name, silently
    discarding the sample's required organism -- a conformant-looking but
    content-empty export (the #146 class of defect).
    """
    docs = to_metabolights(
        _client_with_sample({"name": "SAMP1", "organism": "Homo sapiens"})
    )
    table = _study_table(docs)
    header = table.splitlines()[0]
    assert "Characteristics[Organism]" in header
    assert "Homo sapiens" in table


def test_sample_characteristics_round_trip_through_the_study_table():
    """Authored characteristics and factor values survive export -> read_samples."""
    from metaseed.isatab.reader import read_samples

    docs = to_metabolights(
        _client_with_sample(
            {
                "name": "SAMP1",
                "organism": "Homo sapiens",
                "organism_part": "liver",
                "characteristics": [{"category": "Age", "value": "42"}],
                "factor_values": [{"category": "Dose", "value": "high"}],
            }
        )
    )
    back = read_samples(_study_table(docs))
    assert len(back) == 1
    sample = back[0]
    chars = {c["category"]: c["value"] for c in sample.get("characteristics", [])}
    factors = {f["category"]: f["value"] for f in sample.get("factor_values", [])}
    assert chars.get("Organism") == "Homo sapiens"
    assert chars.get("Organism part") == "liver"
    assert chars.get("Age") == "42"
    assert factors.get("Dose") == "high"
