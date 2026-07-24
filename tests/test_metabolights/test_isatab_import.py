"""Network-free tests for the ISA-Tab fallback import path (issue #146).

The ISA-JSON ``/studies`` payload leaves ``samples``/``dataFiles`` empty, so the
importer recovers Samples, DataFiles and Metabolites from the study's ISA-Tab
files. These tests drive that path with recorded MTBLS1 ``s_``/``a_``/``m_``
fixtures — no live call — and prove the round trip re-emits populated files.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from metaseed.metabolights import to_metabolights
from metaseed.metabolights.mapper import build_dataset

_FIXTURES = Path(__file__).resolve().parents[1] / "test_isatab" / "fixtures"


def _isatab_files() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in _FIXTURES.iterdir()}


def _document() -> dict[str, object]:
    # A minimal ISA-JSON document with EMPTY samples/dataFiles — the real shape
    # MetaboLights returns — so the importer must use the ISA-Tab fallback.
    assay_name = next(n for n in _isatab_files() if n.startswith("a_"))
    return {
        "isaInvestigation": {
            "identifier": "MTBLS1",
            "title": "Investigation",
            "studies": [
                {
                    "identifier": "MTBLS1",
                    "title": "Study",
                    "samples": [],
                    "assays": [{"filename": assay_name, "dataFiles": []}],
                }
            ],
        }
    }


def test_import_recovers_samples_metabolites_and_data_files():
    client = build_dataset(_document(), isatab_files=_isatab_files())
    counts = Counter(e["_type"] for e in client.serialize()["entities"])

    assert counts["Sample"] > 0
    assert counts["Metabolite"] > 0
    assert counts["DataFile"] > 0
    # Characteristics/FactorValues are attached as children of their Sample.
    assert counts["Characteristic"] > 0
    assert counts["FactorValue"] > 0


def test_sample_characteristics_and_factor_values_are_children():
    client = build_dataset(_document(), isatab_files=_isatab_files())
    tree = client.get_tree()

    def find(nodes, entity_type):
        for node in nodes:
            if node.entity_type == entity_type:
                return node
            hit = find(node.children, entity_type)
            if hit:
                return hit
        return None

    sample = find(tree, "Sample")
    assert sample is not None
    child_types = {child.entity_type for child in sample.children}
    assert "Characteristic" in child_types
    assert "FactorValue" in child_types


def test_round_trip_reemits_populated_isatab_files():
    # import (from ISA-Tab) -> to_metabolights -> the s_/a_/m_ files must have
    # data rows, not just headers. This is the exact false positive #96 allowed.
    client = build_dataset(_document(), isatab_files=_isatab_files())
    docs = to_metabolights(client)

    for prefix in ("s_", "a_", "m_"):
        matched = [name for name in docs if name.startswith(prefix)]
        assert matched, f"no {prefix} file emitted"
        for name in matched:
            assert len(docs[name].splitlines()) > 1, f"{name} is header-only"
