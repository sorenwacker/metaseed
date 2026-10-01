"""The import asks the Portal for the three results the profile describes (#284).

The ``ena`` profile declares a Study with analyses and study-level fields, but
the import made one Portal query, ``result=read_run``, from which neither the
Analysis entity nor the columns that exist only under ``result=study`` can be
reached. The exporter writes ``analysis.xml``, so metaseed could emit a document
its own importer never produced, and nothing reported the loss.

Fixtures are recorded from the Portal for PRJEB29581, a marine metagenome study
with thirteen runs and thirteen assemblies; the column lists come from ENA's
``returnFields`` endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from metaseed.ena import build_dataset, import_accession, to_ena_xml
from metaseed.ena.client import EnaClient
from metaseed.specs.loader import SpecLoader

FIXTURES = Path(__file__).parent / "fixtures"
STUDY_ROWS = json.loads((FIXTURES / "study_all_fields.json").read_text())
ANALYSIS_ROWS = json.loads((FIXTURES / "analysis_all_fields.json").read_text())
RUN_ROWS = json.loads((FIXTURES / "read_run.json").read_text())
ANALYSIS_COLUMNS = json.loads((FIXTURES / "analysis_columns.json").read_text())
# Consumed into File entities: the manifests are split per file, and the
# format is written in the SRA schema's spelling ("fasta" for "FASTA").
FILE_MANIFEST_COLUMNS = {
    "submitted_ftp",
    "submitted_md5",
    "submitted_format",
    "generated_ftp",
    "generated_md5",
    "generated_format",
}


def _entities(client) -> list[dict[str, Any]]:
    return client.serialize()["entities"]


def _by_type(client, entity_type: str) -> list[dict[str, Any]]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def _attributes(client, entity_type: str) -> dict[str, str]:
    return {a["tag"]: a["value"] for a in _by_type(client, entity_type)}


def _recorded_values(client) -> set[str]:
    values: set[str] = set()
    for entity in _entities(client):
        for key, value in entity.items():
            if key.startswith("_") or value is None:
                continue
            values.add(str(value))
            if isinstance(value, list):
                values.update(str(v) for v in value)
    return values


# --- the study record -------------------------------------------------------


def test_the_study_record_fills_the_study_not_a_copy_of_its_title():
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS)
    study = _by_type(client, "Study")[0]

    assert study["description"] == STUDY_ROWS[0]["study_description"]
    assert study["description"] != study["title"]
    assert study["center_name"] == "UNIVERSITY OF CAPE TOWN"


def test_study_only_columns_become_study_attributes():
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS)
    attributes = _attributes(client, "StudyAttribute")

    assert attributes["study_name"] == "St Helena Bay_PO_ Meta-omic study"
    assert attributes["secondary_study_center_name"] == "UNIVERSITY OF CAPE TOWN"
    assert attributes["secondary_study_alias"].startswith("ena-STUDY-")


def test_a_study_level_column_is_recorded_once_and_on_the_study():
    """``study_alias`` used to be a run attribute; it is a study attribute, once."""
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS)

    assert "study_alias" in _attributes(client, "StudyAttribute")
    assert "study_alias" not in _attributes(client, "RunAttribute")
    assert [
        a for a in _by_type(client, "StudyAttribute") if a["tag"] == "study_alias"
    ] != []
    assert (
        len(
            [a for a in _by_type(client, "StudyAttribute") if a["tag"] == "study_alias"]
        )
        == 1
    )


def test_a_study_with_no_runs_is_still_a_study():
    client = build_dataset([], study=STUDY_ROWS)

    assert [s["alias"] for s in _by_type(client, "Study")] == ["PRJEB29581"]


# --- analyses -----------------------------------------------------------------


def test_analyses_become_analysis_entities_with_their_files():
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS, analyses=ANALYSIS_ROWS)
    analyses = {a["alias"]: a for a in _by_type(client, "Analysis")}
    assert set(analyses) == {row["analysis_accession"] for row in ANALYSIS_ROWS}

    # Every assembly's generated file is called contig.fa.gz; one analysis
    # keeps the filenames distinct.
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS, analyses=ANALYSIS_ROWS[:1])
    first = _by_type(client, "Analysis")[0]
    assert first["study_ref"] == "PRJEB29581"
    assert first["analysis_type"] == "SEQUENCE_ASSEMBLY"
    assert first["title"] == ANALYSIS_ROWS[0]["analysis_title"]
    assert first["sample_refs"] == [ANALYSIS_ROWS[0]["sample_accession"]]
    assert first["run_refs"] == [ANALYSIS_ROWS[0]["run_accession"]]

    files = {f["filename"]: f for f in _by_type(client, "File") if not f.get("run_ref")}
    submitted = ANALYSIS_ROWS[0]["submitted_ftp"].rsplit("/", 1)[-1]
    generated = ANALYSIS_ROWS[0]["generated_ftp"].rsplit("/", 1)[-1]
    assert files[submitted]["checksum"] == ANALYSIS_ROWS[0]["submitted_md5"]
    assert files[submitted]["filetype"] == "fasta"
    assert files[generated]["checksum"] == ANALYSIS_ROWS[0]["generated_md5"]


def test_an_analysis_row_describes_its_analysis_not_its_sample():
    """The analysis row carries 100 sample columns; those belong to the Sample."""
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS, analyses=ANALYSIS_ROWS)
    tags = set(_attributes(client, "AnalysisAttribute"))

    assert "assembly_type" in tags
    assert "environment_biome" not in tags
    assert "study_alias" not in tags


def test_a_sample_the_runs_did_not_carry_is_made_from_the_analysis_row():
    client = build_dataset([], study=STUDY_ROWS, analyses=ANALYSIS_ROWS)
    samples = {s["alias"]: s for s in _by_type(client, "Sample")}

    assert ANALYSIS_ROWS[0]["sample_accession"] in samples
    sample = samples[ANALYSIS_ROWS[0]["sample_accession"]]
    assert sample["taxon_id"] == int(ANALYSIS_ROWS[0]["tax_id"])
    assert _attributes(client, "SampleAttribute")["environment_biome"] == "marine"


def test_every_non_empty_analysis_column_reaches_the_dataset():
    """The completeness rule, for analysis rows."""
    row = {c: f"value-of-{c}" for c in ANALYSIS_COLUMNS}
    row.update(
        {
            "study_accession": "PRJEB1",
            "analysis_accession": "ERZ1",
            "sample_accession": "SAMEA1",
            "tax_id": "4577",
            "lat": "1.5",
            "lon": "2.5",
            "environmental_sample": "True",
            "submitted_ftp": "ftp.x/a.fasta.gz",
            "submitted_md5": "aaa111",
            "submitted_format": "FASTA",
            "generated_ftp": "ftp.x/contig.fa.gz",
            "generated_md5": "bbb222",
            "generated_format": "FASTA",
        }
    )
    recorded = _recorded_values(build_dataset([], analyses=[row]))

    missing = sorted(
        column
        for column, value in row.items()
        if value and column not in FILE_MANIFEST_COLUMNS and str(value) not in recorded
    )
    assert missing == []


def test_every_non_empty_column_of_the_recorded_analyses_reaches_the_dataset():
    recorded = _recorded_values(
        build_dataset([], study=STUDY_ROWS, analyses=ANALYSIS_ROWS)
    )
    missing = sorted(
        column
        for column, value in ANALYSIS_ROWS[0].items()
        if value and column not in FILE_MANIFEST_COLUMNS and str(value) not in recorded
    )
    assert missing == []


# --- the client and the wiring --------------------------------------------------


def _portal(requests: list[str]) -> EnaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        result = request.url.params["result"]
        requests.append(result)
        # The Portal rejects a run or sample accession on these two results.
        if result != "read_run":
            assert request.url.params["accession"].startswith("PRJ"), request.url
        payload = {
            "read_run": RUN_ROWS,
            "study": STUDY_ROWS,
            "analysis": ANALYSIS_ROWS,
        }[result]
        assert request.url.params["fields"] == "all"
        return httpx.Response(200, json=payload)

    return EnaClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_client_asks_each_result_with_every_column():
    requests: list[str] = []
    client = _portal(requests)

    assert client.study("PRJEB29581") == STUDY_ROWS
    assert client.analysis("PRJEB29581") == ANALYSIS_ROWS
    assert requests == ["study", "analysis"]


def test_an_import_is_three_requests_whatever_the_study_holds():
    requests: list[str] = []
    client = import_accession("PRJEB29581", client=_portal(requests))

    assert sorted(requests) == ["analysis", "read_run", "study"]
    assert len(_by_type(client, "Analysis")) == len(ANALYSIS_ROWS)
    assert len(_by_type(client, "Run")) == len(RUN_ROWS)


def test_a_run_accession_is_resolved_to_its_study_before_the_other_results():
    """``result=study`` and ``result=analysis`` take a study accession only."""
    requests: list[str] = []
    client = import_accession(RUN_ROWS[0]["run_accession"], client=_portal(requests))

    assert sorted(requests) == ["analysis", "read_run", "study"]
    assert _by_type(client, "Analysis") != []


def test_an_accession_with_no_runs_and_no_study_shape_asks_nothing_more():
    """A sample accession that resolves to no runs cannot name a study; the
    Portal would answer the other two results with 400."""
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["result"])
        return httpx.Response(200, json=[])

    client = EnaClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    dataset = import_accession("SAMEA0000000", client=client)

    assert requests == ["read_run"]
    assert dataset.get_roots() == []


def test_a_study_without_analyses_is_an_empty_answer_not_a_missing_query(caplog):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        result = request.url.params["result"]
        requests.append(result)
        return httpx.Response(
            200,
            json=[]
            if result == "analysis"
            else {"read_run": RUN_ROWS, "study": STUDY_ROWS}[result],
        )

    client = EnaClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with caplog.at_level("INFO", logger="metaseed.ena"):
        dataset = import_accession("PRJEB29581", client=client)

    assert "analysis" in requests
    assert _by_type(dataset, "Analysis") == []
    assert "0 analyses" in caplog.text


# --- the round trip -----------------------------------------------------------


def test_imported_analyses_survive_the_export():
    """What the importer builds, the exporter emits — including analyses."""
    client = build_dataset(RUN_ROWS, study=STUDY_ROWS, analyses=ANALYSIS_ROWS)
    documents = to_ena_xml(client)

    assert "analysis.xml" in documents
    root = ET.fromstring(documents["analysis.xml"])
    aliases = {a.get("alias") for a in root.findall("ANALYSIS")}
    assert aliases == {row["analysis_accession"] for row in ANALYSIS_ROWS}
    first = root.find("ANALYSIS")
    assert first.find("STUDY_REF").get("refname") == "PRJEB29581"
    assert first.find("ANALYSIS_TYPE/SEQUENCE_ASSEMBLY") is not None
    checksums = {f.get("checksum") for f in first.findall("FILES/FILE")}
    assert ANALYSIS_ROWS[0]["submitted_md5"] in checksums

    study = ET.fromstring(documents["study.xml"]).find("STUDY")
    tags = {
        a.findtext("TAG") for a in study.findall("STUDY_ATTRIBUTES/STUDY_ATTRIBUTE")
    }
    assert "study_name" in tags


# --- the promise the profile makes ----------------------------------------------


def test_the_three_sample_fields_the_portal_never_publishes_are_the_documented_ones():
    """``common_name``, ``geographic_location_region`` and ``lab_host`` have no
    column under any Portal result; the import docs say so, and nothing else
    is in that position."""
    spec = SpecLoader(profile="ena").load_profile("1.0", "ena")
    from metaseed.ena.mapper import SAMPLE_FIELDS

    columns: set[str] = set()
    for name in (
        "read_run_columns",
        "sample_columns",
        "study_columns",
        "analysis_columns",
    ):
        columns |= set(json.loads((FIXTURES / f"{name}.json").read_text()))
    declared = {f.name for f in spec.entities["Sample"].fields if not f.is_nested()}
    reachable = set(SAMPLE_FIELDS.values()) | {"alias", "accession", "study_ref"}
    assert set(SAMPLE_FIELDS) <= columns
    assert declared - reachable == {
        "common_name",
        "geographic_location_region",
        "lab_host",
    }
