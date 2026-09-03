"""Tests for the ENA exporter (ena dataset -> ENA submission XML)."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from metaseed.ena import to_ena_xml
from metaseed.ena.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "read_run.json"


def _dataset():
    return build_dataset(json.loads(FIXTURE.read_text()))


def test_export_produces_well_formed_submission_documents():
    docs = to_ena_xml(_dataset())

    # submission.xml always accompanies the content documents: Webin acts on the
    # SUBMISSION, and the rest do nothing without it. This fixture has no
    # Analysis, so no analysis.xml.
    assert set(docs) == {
        "study.xml",
        "sample.xml",
        "experiment.xml",
        "run.xml",
        "submission.xml",
    }
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


@pytest.mark.network
def test_ena_export_validates_against_official_sra_xsd():
    """The exported XML conforms to ENA's official SRA schemas (would be
    accepted). Opt-in: needs network + xmlschema (a dev dependency)."""
    xmlschema = pytest.importorskip("xmlschema")
    from metaseed.ena import import_accession

    docs = to_ena_xml(import_accession("ERR164407"))
    base = (
        "https://raw.githubusercontent.com/enasequence/schema/master/"
        "src/main/resources/uk/ac/ebi/ena/sra/schema/"
    )
    for doc, xsd in [
        ("study.xml", "SRA.study.xsd"),
        ("sample.xml", "SRA.sample.xsd"),
        ("experiment.xml", "SRA.experiment.xsd"),
        ("run.xml", "SRA.run.xsd"),
        ("submission.xml", "SRA.submission.xsd"),
    ]:
        if doc not in docs:
            continue
        schema = xmlschema.XMLSchema(base + xsd, base_url=base)
        schema.validate(docs[doc])  # raises XMLSchemaValidationError if invalid


class TestTagNamesAreAlwaysWellFormed:
    """A draft value must not serialize into unparseable XML.

    library_layout/platform were used as raw element tag names; ElementTree
    validates nothing, so a draft value like 'Illumina HiSeq' produced
    '<ILLUMINA HISEQ/>' — malformed XML emitted with no error, which ENA
    rejects with no hint of the cause. The tag is sanitized to a well-formed
    name; the value itself is still the enum validation's job.
    """

    def test_a_spaced_platform_still_parses(self):
        from metaseed import MetaseedClient

        client = MetaseedClient("ena", "1.0")
        study = client.create_entity(
            "Study", {"alias": "S1", "title": "t"}, skip_validation=True
        )
        client.create_entity(
            "Experiment",
            {
                "alias": "E1",
                "platform": "Illumina HiSeq",
                "library_layout": "paired end",
            },
            parent_id=study.id,
            skip_validation=True,
        )

        parsed = ET.fromstring(to_ena_xml(client)["experiment.xml"])

        # The spaced draft value became one well-formed element name.
        assert parsed.find("EXPERIMENT/PLATFORM/ILLUMINA_HISEQ") is not None
        assert (
            parsed.find(
                "EXPERIMENT/DESIGN/LIBRARY_DESCRIPTOR/LIBRARY_LAYOUT/PAIRED_END"
            )
            is not None
        )
