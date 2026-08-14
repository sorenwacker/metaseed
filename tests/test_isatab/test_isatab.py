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


def test_multi_study_investigation_partitions_children_per_study():
    """Each study's sections contain only its own factors/contacts — a
    multi-study investigation must not duplicate every child into every study.
    """
    from metaseed import MetaseedClient

    client = MetaseedClient("metabolights", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "INV1", "title": "Inv"}, skip_validation=True
    )
    s1 = client.create_entity(
        "Study",
        {"identifier": "S1", "title": "One"},
        parent_id=inv.id,
        skip_validation=True,
    )
    s2 = client.create_entity(
        "Study",
        {"identifier": "S2", "title": "Two"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Factor", {"name": "FactorA"}, parent_id=s1.id, skip_validation=True
    )
    client.create_entity(
        "Factor", {"name": "FactorB"}, parent_id=s2.id, skip_validation=True
    )

    inv_txt = to_isatab(client)["i_Investigation.txt"]

    # Each factor belongs to exactly one study, so it appears once, not once per study.
    assert inv_txt.count("FactorA") == 1
    assert inv_txt.count("FactorB") == 1


def test_the_investigation_names_its_study_files():
    """Each STUDY section carries 'Study File Name' pointing at its s_*.txt.

    to_isatab writes an s_<study>.txt per study, but the investigation never
    referenced them — ISA-Tab consumers locate the study table through this
    field, so the emitted study files were orphans and the archive could not
    be parsed as complete ISA-Tab.
    """
    files = to_isatab(_client())

    investigation = files["i_Investigation.txt"]
    study_files = [name for name in files if name.startswith("s_")]
    assert study_files
    assert "Study File Name" in investigation
    for name in study_files:
        assert name in investigation
