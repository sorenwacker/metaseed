"""Tests for the MetaboLights exporter (ISA-Tab + MAF)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed.metabolights import to_metabolights
from metaseed.metabolights.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "study.json"


def _client():
    return build_dataset(json.loads(FIXTURE.read_text()))


def test_to_metabolights_includes_isatab_and_a_maf():
    docs = to_metabolights(_client())
    assert "i_Investigation.txt" in docs

    maf = [n for n in docs if "maf" in n.lower() or n.startswith("m_")]
    assert maf, f"no MAF document in {list(docs)}"
    assert "metabolite_identification" in docs[maf[0]]  # standard MAF header
