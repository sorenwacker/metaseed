"""Tests for the shared ISA-Tab exporter (pure, no network)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed.isatab import to_isatab
from metaseed.metabolights.mapper import build_dataset

FIXTURE = Path(__file__).parent.parent / "test_metabolights" / "fixtures" / "study.json"


def _client():
    return build_dataset(json.loads(FIXTURE.read_text()))


def test_investigation_file_has_the_isatab_sections():
    inv = to_isatab(_client())["i_Investigation.txt"]
    for section in [
        "ONTOLOGY SOURCE REFERENCE",
        "INVESTIGATION",
        "STUDY",
        "STUDY FACTORS",
        "STUDY ASSAYS",
        "STUDY PROTOCOLS",
        "STUDY CONTACTS",
    ]:
        assert section in inv


def test_investigation_file_carries_real_values():
    client = _client()
    ents = client.serialize()["entities"]
    inv = to_isatab(client)["i_Investigation.txt"]

    study_title = next(
        e["title"] for e in ents if e["_type"] == "Study" and e.get("title")
    )
    assert study_title in inv

    people = [e for e in ents if e["_type"] == "Person" and e.get("last_name")]
    assert people, "fixture should have study-level people"
    assert people[0]["last_name"] in inv  # study contacts are emitted


def test_study_and_assay_files_are_emitted():
    docs = to_isatab(_client())
    assert any(name.startswith("s_") for name in docs)
    assert any(name.startswith("a_") for name in docs)
