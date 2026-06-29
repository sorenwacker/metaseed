"""Tests for the PRIDE exporter (pride dataset -> submission.px)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed.pride import to_pride_submission
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
