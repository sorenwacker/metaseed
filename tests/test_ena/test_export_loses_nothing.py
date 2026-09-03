"""The ENA export must carry every entity the dataset holds.

The exporter handled five of the profile's eleven entity types, so exporting the
shipped example silently dropped 55 of its 89 entities: every SampleAttribute,
ExperimentAttribute, RunAttribute and AnalysisAttribute, both ProjectLinks, and
the Analysis. Nothing reported it — the XML looked complete.

That is not a fidelity nicety. ENA registers a sample against a *checklist*, and
a checklist's mandatory fields (collection date, geographic location, ...) are
carried as sample attributes, so a SAMPLE_SET without them is rejected on
submission. An export that drops them produces a file that cannot be submitted
and gives no hint why.

These tests read the shipped example rather than a fixture built here: it is the
dataset a user actually exports, and it exercises every entity type.
"""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from metaseed import MetaseedClient
from metaseed.ena import to_ena_xml
from metaseed.profiles import ProfileFactory

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "src/metaseed/examples/ena/1.0/arabidopsis-drought-rnaseq.yaml"
)


@pytest.fixture(scope="module")
def client() -> MetaseedClient:
    facade = ProfileFactory().create("ena", "1.0")
    facade.load_nested(copy.deepcopy(yaml.safe_load(EXAMPLE.read_text())), "Study")
    return MetaseedClient.from_facade(facade)


@pytest.fixture(scope="module")
def documents(client: MetaseedClient) -> dict[str, str]:
    return to_ena_xml(client)


def _counts(client: MetaseedClient) -> Counter[str]:
    return Counter(e["_type"] for e in client.serialize()["entities"])


def test_the_example_still_exercises_every_entity_type(client: MetaseedClient) -> None:
    """Guard the guard: these tests mean nothing if the example thins out."""
    counts = _counts(client)
    assert counts["SampleAttribute"] >= 1
    assert counts["ExperimentAttribute"] >= 1
    assert counts["RunAttribute"] >= 1
    assert counts["AnalysisAttribute"] >= 1
    assert counts["ProjectLink"] >= 1
    assert counts["Analysis"] >= 1


def test_every_entity_type_reaches_the_xml(
    client: MetaseedClient, documents: dict[str, str]
) -> None:
    """No entity type present in the dataset may be missing from the export."""
    xml = "\n".join(documents.values())
    # An entity is represented when a value only it supplies appears in the XML.
    probes = {
        "SampleAttribute": "tag",
        "ExperimentAttribute": "tag",
        "RunAttribute": "tag",
        "AnalysisAttribute": "tag",
        "ProjectLink": "id",
        "Analysis": "alias",
    }
    missing = []
    for entity in client.serialize()["entities"]:
        field = probes.get(entity["_type"])
        value = entity.get(field) if field else None
        if value and str(value) not in xml:
            missing.append(f"{entity['_type']}.{field}={value!r}")
    assert not missing, f"{len(missing)} entities never reach the XML: {missing[:8]}"


def test_sample_attributes_hang_from_the_sample_that_owns_them(
    documents: dict[str, str],
) -> None:
    """A flat by-type grouping cannot say which sample an attribute belongs to."""
    samples = {s.get("alias"): s for s in ET.fromstring(documents["sample.xml"])}
    sample = samples["SAMEA-COL0-0H-REP1"]
    attributes = {
        a.findtext("TAG"): a.findtext("VALUE")
        for a in sample.findall("SAMPLE_ATTRIBUTES/SAMPLE_ATTRIBUTE")
    }
    assert attributes.get("treatment") == "well-watered control"
    assert attributes.get("biological_replicate") == "1"
    # The drought sample keeps its own values rather than inheriting the first's.
    other = samples["SAMEA-COL0-72H-REP1"]
    other_attributes = {
        a.findtext("TAG"): a.findtext("VALUE")
        for a in other.findall("SAMPLE_ATTRIBUTES/SAMPLE_ATTRIBUTE")
    }
    assert other_attributes.get("treatment") == "severe drought stress"
    assert other_attributes.get("soil_water_content") == "15"


def test_an_attribute_keeps_its_units(documents: dict[str, str]) -> None:
    """UNITS is a real ENA element; dropping it changes what a value means."""
    xml = documents["sample.xml"]
    root = ET.fromstring(xml)
    with_units = [
        a
        for a in root.iter("SAMPLE_ATTRIBUTE")
        if a.findtext("UNITS") not in (None, "")
    ]
    assert with_units, "no SAMPLE_ATTRIBUTE carries UNITS"


def test_experiment_and_run_attributes_are_emitted(
    documents: dict[str, str],
) -> None:
    experiment = ET.fromstring(documents["experiment.xml"])
    assert list(experiment.iter("EXPERIMENT_ATTRIBUTE")), "no EXPERIMENT_ATTRIBUTE"
    run = ET.fromstring(documents["run.xml"])
    assert list(run.iter("RUN_ATTRIBUTE")), "no RUN_ATTRIBUTE"


def test_project_links_become_study_links(documents: dict[str, str]) -> None:
    study = ET.fromstring(documents["study.xml"]).find("STUDY")
    links = study.findall("STUDY_LINKS/STUDY_LINK/XREF_LINK")
    assert links, "ProjectLinks did not become STUDY_LINKS"
    assert any(link.findtext("DB") for link in links)


def test_analysis_is_exported_with_its_attributes(documents: dict[str, str]) -> None:
    assert "analysis.xml" in documents, (
        "an Analysis in the dataset produced no ANALYSIS_SET"
    )
    root = ET.fromstring(documents["analysis.xml"])
    assert root.tag == "ANALYSIS_SET"
    assert root.find("ANALYSIS") is not None
    assert list(root.iter("ANALYSIS_ATTRIBUTE")), "no ANALYSIS_ATTRIBUTE"


def test_a_submission_document_drives_the_upload(documents: dict[str, str]) -> None:
    """Webin needs a SUBMISSION naming an action per document, or nothing runs."""
    assert "submission.xml" in documents
    root = ET.fromstring(documents["submission.xml"])
    assert root.tag == "SUBMISSION"
    schemas = {add.get("schema") for add in root.findall("ACTIONS/ACTION/ADD")}
    # One ADD per emitted content document (submission.xml itself excluded).
    assert "study" in schemas and "sample" in schemas


def test_an_experiment_without_a_design_description_still_conforms(
    documents: dict[str, str],
) -> None:
    """``DESIGN_DESCRIPTION`` is mandatory and must come first in ``DESIGN``.

    Omitting it when the field was empty left ``SAMPLE_DESCRIPTOR`` in first
    position, which ENA's SRA.experiment schema rejects — caught by validating
    the export against the official XSD, not by the XML parsing cleanly.
    """
    experiments = ET.fromstring(documents["experiment.xml"]).findall("EXPERIMENT")
    assert len(experiments) > 1
    for experiment in experiments:
        design = experiment.find("DESIGN")
        assert design is not None
        assert design[0].tag == "DESIGN_DESCRIPTION", (
            f"{experiment.get('alias')}: DESIGN starts with {design[0].tag}"
        )


def test_every_document_is_well_formed(documents: dict[str, str]) -> None:
    for name, xml in documents.items():
        ET.fromstring(xml)  # raises if malformed
        assert xml.startswith("<?xml"), f"{name} has no XML declaration"
