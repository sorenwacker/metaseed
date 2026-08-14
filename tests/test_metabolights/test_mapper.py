"""Tests for the MetaboLights study -> metabolights-profile mapper (no network)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from metaseed.metabolights.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "study.json"


def _study() -> dict:
    return json.loads(FIXTURE.read_text())


def _entities(client) -> list[dict]:
    return client.serialize()["entities"]


def _by_type(client, entity_type: str) -> list[dict]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def test_build_dataset_creates_the_full_hierarchy():
    client = build_dataset(_study())

    counts = Counter(e["_type"] for e in _entities(client))
    assert counts["Investigation"] == 1
    assert counts["Person"] == 2
    assert counts["Publication"] == 1
    assert counts["Study"] == 1
    assert counts["Factor"] == 2
    assert counts["Protocol"] == 2
    assert counts["Sample"] == 1
    assert counts["Assay"] == 1
    assert counts["DataFile"] == 1


def test_investigation_and_study_fields_are_mapped():
    client = build_dataset(_study())

    inv = _by_type(client, "Investigation")[0]
    assert inv["identifier"] == "MTBLS1"
    assert inv["accession"] == "MTBLS1"
    assert inv["title"].startswith("A metabolomic study")
    assert inv["public_release_date"] == "2012-02-14"

    study = _by_type(client, "Study")[0]
    assert study["identifier"] == "MTBLS1"
    assert study["study_design_descriptors"] == [
        "diabetes mellitus",
        "untargeted metabolites",
        "NMR spectroscopy",
    ]


def test_people_publications_factors_and_protocols_are_mapped():
    client = build_dataset(_study())

    people = {p["last_name"]: p for p in _by_type(client, "Person")}
    assert people["Carter"]["email"] == "s.carter@example.org"
    assert people["Carter"]["roles"] == ["principal investigator role"]

    publication = _by_type(client, "Publication")[0]
    assert publication["doi"] == "10.1152/physiolgenomics.90264.2008"
    assert publication["status"] == "Published"

    factors = {f["name"]: f for f in _by_type(client, "Factor")}
    assert factors["Gender"]["factor_type"] == "Gender"

    protocols = {p["name"]: p for p in _by_type(client, "Protocol")}
    assert protocols["NMR spectroscopy"]["protocol_type"] == "NMR spectroscopy"

    # Only named parameters become entities; the empty placeholder is dropped.
    params = {p["name"] for p in _by_type(client, "ProtocolParameter")}
    assert params == {"Instrument", "NMR tube type"}


def test_sample_organism_and_characteristics_are_mapped():
    client = build_dataset(_study())

    sample = _by_type(client, "Sample")[0]
    assert sample["name"] == "ADG10003u_007"
    assert sample["organism"] == "Homo sapiens"
    assert sample["organism_part"] == "urine"
    # organism_term is left unset: resolving it would hit OLS4 (network).
    assert "organism_term" not in sample

    categories = {c["category"] for c in _by_type(client, "Characteristic")}
    assert {"Organism", "Organism part"} <= categories

    factor_value = _by_type(client, "FactorValue")[0]
    assert factor_value["factor_name"] == "Gender"
    assert factor_value["value"] == "Male"


def test_assay_references_raw_files_as_urls_not_downloads():
    client = build_dataset(_study())

    assay = _by_type(client, "Assay")[0]
    assert assay["filename"].startswith("a_MTBLS1")
    assert assay["technology_type"] == "NMR spectroscopy"
    assert assay["measurement_type"] == "metabolite profiling"
    assert assay["samples"] == ["ADG10003u_007"]
    assert assay["metabolite_assignment_file"].endswith("_maf.tsv")

    data_file = _by_type(client, "DataFile")[0]
    assert data_file["filename"] == (
        "http://ftp.ebi.ac.uk/pub/databases/metabolights/studies/public/MTBLS1"
        "/ADG10003u_007.zip"
    )
    assert data_file["file_type"] == "Raw Spectral Data File"


def test_empty_document_yields_empty_dataset():
    assert build_dataset({}).serialize()["entities"] == []
    assert build_dataset({"isaInvestigation": {}}).serialize()["entities"] == []


class TestMafSelectionHonorsTheDeclaredFile:
    """Each assay imports metabolites from ITS OWN declared MAF.

    The MAF was selected by "the sole m_* file": a multi-MAF study (the
    normal MetaboLights layout for multi-assay studies) imported no
    metabolites at all, and a single-MAF multi-assay study attached the same
    metabolites to every assay — even though each assay's exact MAF name was
    parsed from its comments and stored beside the choice being made.
    """

    _MAF = (
        "database_identifier\tchemical_formula\tsmiles\tinchi\t"
        "metabolite_identification\n"
        "CHEBI:{n}\tC6H12O6\t-\t-\tmetabolite-{n}\n"
    )

    def _study_with_two_assays(self) -> dict:
        study = _study()
        assay = json.loads(
            json.dumps(study["isaInvestigation"]["studies"][0]["assays"][0])
        )
        assay["filename"] = "a_second.txt"
        assay["comments"] = [
            {"name": "Metabolite Assignment File", "value": "m_second_maf.tsv"}
        ]
        study["isaInvestigation"]["studies"][0]["assays"].append(assay)
        return study

    def test_two_assays_each_get_their_own_maf(self):
        study = self._study_with_two_assays()
        isatab = {
            "m_MTBLS1_NMR_metabolite_profiling_v2_maf.tsv": self._MAF.format(n=1),
            "m_second_maf.tsv": self._MAF.format(n=2),
        }

        client = build_dataset(study, isatab_files=isatab)

        assays = _by_type(client, "Assay")
        metabolites = _by_type(client, "Metabolite")
        assert metabolites, "a multi-MAF study must import metabolites"
        names = {m.get("metabolite_identification") for m in metabolites}
        assert names == {"metabolite-1", "metabolite-2"}
        assert len(assays) == 2
