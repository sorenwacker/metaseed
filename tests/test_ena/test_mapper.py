"""Tests for the ENA read_run -> ena-profile mapper (pure, no network)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from metaseed.ena.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "read_run.json"


def _rows():
    return json.loads(FIXTURE.read_text())


def _entities(client) -> list[dict]:
    return client.serialize()["entities"]


def _by_type(client, entity_type: str) -> list[dict]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def test_build_dataset_creates_the_full_hierarchy():
    client = build_dataset(_rows())

    counts = Counter(e["_type"] for e in _entities(client))
    assert counts["Study"] == 1
    assert counts["Sample"] == 2
    assert counts["Experiment"] == 2
    assert counts["Run"] == 2
    assert counts["File"] == 3  # 2 fastq for ERR001 + 1 for ERR002


def test_accessions_and_references_are_mapped():
    client = build_dataset(_rows())

    study = _by_type(client, "Study")[0]
    assert study["accession"] == "PRJEB10000"

    samples = {s["alias"]: s for s in _by_type(client, "Sample")}
    assert samples["SAMEA001"]["study_ref"] == "PRJEB10000"
    assert samples["SAMEA001"]["scientific_name"] == "Zea mays"
    assert samples["SAMEA001"]["taxon_id"] == 4577  # coerced from the string "4577"

    runs = {r["alias"]: r for r in _by_type(client, "Run")}
    assert runs["ERR001"]["experiment_ref"] == "ERX001"


def test_files_reference_runs_and_carry_checksums_not_downloads():
    client = build_dataset(_rows())

    err001 = [f for f in _by_type(client, "File") if f["run_ref"] == "ERR001"]
    assert len(err001) == 2
    assert {f["filename"] for f in err001} == {
        "ERR001_1.fastq.gz",
        "ERR001_2.fastq.gz",
    }
    assert all(f["checksum_method"] == "MD5" for f in err001)
    assert {f["checksum"] for f in err001} == {"aaa111", "bbb222"}


def test_empty_rows_yield_empty_dataset():
    client = build_dataset([])
    assert client.serialize()["entities"] == []


def test_file_checksums_stay_aligned_when_a_url_segment_is_empty():
    """fastq_ftp/fastq_md5 are parallel lists; an empty URL segment must not
    shift the checksums (they are paired positionally)."""
    rows = [
        {
            "study_accession": "PRJEB1",
            "run_accession": "ERR1",
            "fastq_ftp": "ftp.x/a_1.fastq.gz;;ftp.x/a_3.fastq.gz",
            "fastq_md5": "aaa;bbb;ccc",
        }
    ]
    files = {
        e["filename"]: e
        for e in build_dataset(rows).serialize()["entities"]
        if e["_type"] == "File"
    }
    assert len(files) == 2  # the empty URL segment is skipped
    assert files["a_1.fastq.gz"]["checksum"] == "aaa"
    assert files["a_3.fastq.gz"]["checksum"] == "ccc"  # not the middle "bbb"
