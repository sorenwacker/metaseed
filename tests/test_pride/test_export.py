"""Tests for the PRIDE exporter (pride dataset -> submission.px)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed import MetaseedClient
from metaseed.pride import to_pride_sdrf, to_pride_submission
from metaseed.pride.mapper import build_dataset

FIXTURES = Path(__file__).parent / "fixtures"


def _project() -> dict:
    return json.loads((FIXTURES / "project.json").read_text())


def _files() -> list[dict]:
    return json.loads((FIXTURES / "files.json").read_text())


def _submission() -> str:
    client = build_dataset(_project(), _files())
    return to_pride_submission(client)["submission.px"]


def _mtd(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("MTD\t"):
            _, key, value = line.split("\t", 2)
            rows.setdefault(key, []).append(value)
    return rows


def test_submission_has_header_and_is_tab_separated():
    text = _submission()
    assert text.startswith("# PRIDE submission.px")
    assert "FMH\tfile_id\tfile_type\tfile_path" in text  # file-mapping header
    assert all(
        line.startswith(("# ", "MTD\t", "FMH\t", "FME\t"))
        for line in text.splitlines()
        if line
    )


def test_metadata_lines_carry_project_and_submitter_fields():
    mtd = _mtd(_submission())

    assert mtd["project_title"][0].startswith("TMT spikes")
    assert mtd["submission_type"] == ["COMPLETE"]
    assert mtd["submitter_name"] == ["Laurent Gatto"]
    assert mtd["submitter_email"] == ["lg390@cam.ac.uk"]
    assert mtd["lab_head_name"] == ["Kathryn Lilley"]
    assert mtd["keywords"] == ["Spikes, Tmt, Eriwinia"]


def test_species_instruments_and_modifications_are_emitted():
    mtd = _mtd(_submission())

    assert mtd["species"] == ["Erwinia carotovora"]
    assert mtd["instrument"] == ["LTQ Orbitrap Velos"]
    assert "monohydroxylated residue" in mtd["modification"]


def test_files_become_fme_lines():
    fme = [
        line.split("\t")
        for line in _submission().splitlines()
        if line.startswith("FME\t")
    ]

    assert len(fme) == 3
    # FME columns: file_id, file_type, file_path
    file_ids = [row[1] for row in fme]
    assert file_ids == ["0", "1", "2"]

    by_path = {row[3]: row for row in fme}
    raw = by_path["TMT_Erwinia_1uLSike_Top10HCD_isol2_45stepped_60min_01.raw"]
    assert raw[2] == "RAW"  # file_type column
    assert "PRIDE_Exp_Complete_Ac_22134.pride.mgf.gz" in by_path


def test_empty_dataset_yields_no_submission():
    client = build_dataset({}, [])
    assert to_pride_submission(client) == {}


# --- SDRF-Proteomics export -------------------------------------------------


def _sdrf_client() -> MetaseedClient:
    """A pride dataset with samples and sample-linked files (Archive has none)."""
    client = MetaseedClient("pride", "1.0")
    client.create_entity(
        "Dataset",
        {
            "accession": "PXD000001",
            "title": "SDRF test",
            "description": "d",
            "instruments": [{"name": "LTQ Orbitrap"}],
            "samples": [
                {
                    "name": "S1",
                    "species": "Homo sapiens",
                    "ncbi_taxonomy_id": "9606",
                    "tissue": "liver",
                    "disease": "normal",
                    "custom_attributes": [{"name": "age", "value": "45"}],
                },
                {
                    "name": "S2",
                    "species": "Homo sapiens",
                    "ncbi_taxonomy_id": "9606",
                    "cell_type": "hepatocyte",
                },
            ],
            "files": [
                {"filename": "run1.raw", "file_type": "RAW", "sample_refs": ["S1"]},
                {
                    "filename": "run2.raw",
                    "file_type": "RAW",
                    "sample_refs": ["S1", "S2"],
                },
            ],
        },
        skip_validation=True,
    )
    return client


def _sdrf_rows() -> list[list[str]]:
    text = to_pride_sdrf(_sdrf_client())["sdrf.tsv"]
    return [line.split("\t") for line in text.splitlines()]


def test_sdrf_header_has_expected_columns():
    header = _sdrf_rows()[0]
    assert header[0] == "source name"
    assert "characteristics[organism]" in header
    assert "characteristics[organism part]" in header
    assert "characteristics[disease]" in header
    # Custom attributes become characteristics columns.
    assert "characteristics[age]" in header
    assert "assay name" in header
    assert "technology type" in header
    assert "comment[data file]" in header
    assert "comment[instrument]" in header


def test_sdrf_is_rectangular_and_tab_separated():
    rows = _sdrf_rows()
    width = len(rows[0])
    assert width > 1
    assert all(len(row) == width for row in rows)


def test_sdrf_one_row_per_sample_file_pair():
    rows = _sdrf_rows()[1:]  # drop header
    # S1 -> run1.raw + run2.raw (2 rows); S2 -> run2.raw (1 row) = 3 rows.
    assert len(rows) == 3
    source_col = [r[0] for r in rows]
    assert source_col.count("S1") == 2
    assert source_col.count("S2") == 1


def test_sdrf_renders_values_and_na_for_missing():
    header = _sdrf_rows()[0]
    rows = _sdrf_rows()[1:]
    org_part = header.index("characteristics[organism part]")
    age = header.index("characteristics[age]")
    data_file = header.index("comment[data file]")

    s1 = next(r for r in rows if r[0] == "S1")
    s2 = next(r for r in rows if r[0] == "S2")
    assert s1[org_part] == "liver"
    assert s1[age] == "45"
    assert s2[org_part] == "not available"  # S2 has no tissue
    assert s2[age] == "not available"  # S2 has no age attribute
    assert {r[data_file] for r in rows} == {"run1.raw", "run2.raw"}


def test_sdrf_technology_type_is_constant():
    header = _sdrf_rows()[0]
    rows = _sdrf_rows()[1:]
    tech = header.index("technology type")
    assert {r[tech] for r in rows} == {"proteomic profiling by mass spectrometry"}


def test_sdrf_empty_without_dataset():
    # No project -> no Dataset entity -> no SDRF.
    client = build_dataset({}, [])
    assert to_pride_sdrf(client) == {}


def test_sdrf_from_archive_fixture_uses_synthesized_sample():
    # The mapper synthesizes one project-level sample from the Archive record,
    # so a real imported dataset still yields a single-row SDRF.
    rows = [
        line.split("\t")
        for line in to_pride_sdrf(build_dataset(_project(), _files()))[
            "sdrf.tsv"
        ].splitlines()
    ]
    assert rows[0][0] == "source name"
    assert len(rows) - 1 >= 1  # at least one sample row
    organism = rows[0].index("characteristics[organism]")
    assert rows[1][organism] == "Erwinia carotovora"
