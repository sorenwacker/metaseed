"""Tests for the ENA exporter (ena dataset -> ENA submission XML)."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from metaseed.ena import to_ena_xml
from metaseed.ena.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "read_run.json"


def _dataset():
    return build_dataset(json.loads(FIXTURE.read_text()))


def test_export_produces_well_formed_submission_documents():
    docs = to_ena_xml(_dataset())

    assert set(docs) == {"study.xml", "sample.xml", "experiment.xml", "run.xml"}
    # every document must be parseable XML
    roots = {name: ET.fromstring(xml) for name, xml in docs.items()}
    assert roots["study.xml"].tag == "STUDY_SET"
    assert roots["run.xml"].tag == "RUN_SET"


def test_study_and_sample_carry_their_fields():
    docs = to_ena_xml(_dataset())

    study = ET.fromstring(docs["study.xml"]).find("STUDY")
    assert study.get("alias") == "PRJEB10000"
    assert study.findtext("DESCRIPTOR/STUDY_TITLE") == "Example drought RNA-seq"

    samples = {s.get("alias"): s for s in ET.fromstring(docs["sample.xml"])}
    assert samples["SAMEA001"].findtext("SAMPLE_NAME/TAXON_ID") == "4577"
    assert samples["SAMEA001"].findtext("SAMPLE_NAME/SCIENTIFIC_NAME") == "Zea mays"


def test_experiment_references_and_library_descriptor():
    exp = ET.fromstring(to_ena_xml(_dataset())["experiment.xml"]).find("EXPERIMENT")
    assert exp.find("STUDY_REF").get("refname") == "PRJEB10000"
    assert exp.find("DESIGN/SAMPLE_DESCRIPTOR").get("refname") == "SAMEA001"
    assert exp.findtext("DESIGN/LIBRARY_DESCRIPTOR/LIBRARY_STRATEGY") == "RNA-Seq"
    assert exp.find("DESIGN/LIBRARY_DESCRIPTOR/LIBRARY_LAYOUT/PAIRED") is not None
    assert exp.findtext("PLATFORM/ILLUMINA/INSTRUMENT_MODEL") == "Illumina HiSeq 2500"


def test_runs_reference_files_with_checksums():
    run_set = ET.fromstring(to_ena_xml(_dataset())["run.xml"])
    runs = {r.get("alias"): r for r in run_set}

    assert runs["ERR001"].find("EXPERIMENT_REF").get("refname") == "ERX001"
    files = runs["ERR001"].findall("DATA_BLOCK/FILES/FILE")
    assert {f.get("filename") for f in files} == {
        "ERR001_1.fastq.gz",
        "ERR001_2.fastq.gz",
    }
    assert all(f.get("checksum_method") == "MD5" for f in files)


def test_roundtrip_import_then_export_is_well_formed():
    # import (mapper) -> export (xml) must round-trip without error
    docs = to_ena_xml(_dataset())
    for xml in docs.values():
        ET.fromstring(xml)  # no exception
