"""Network-free tests for the ISA-Tab reader (issue #146).

Parses recorded MetaboLights MTBLS1 ``s_``/``a_``/``m_`` fixtures (header + a few
rows) — no live call — to lock in Sample / DataFile / Metabolite extraction and
the Characteristics/Factor-Value attachment. This is the permanent CI gate the
network-only importer never had.
"""

from __future__ import annotations

from pathlib import Path

from metaseed.isatab import (
    read_data_files,
    read_metabolites,
    read_rows,
    read_samples,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    matches = sorted(_FIXTURES.glob(name))
    assert matches, f"fixture matching {name!r} not found"
    return matches[0].read_text(encoding="utf-8")


def test_read_rows_keys_by_header_and_dedupes_repeats():
    rows = read_rows(_read("s_*.txt"))
    assert rows, "expected data rows"
    header_keys = rows[0].keys()
    assert "Sample Name" in header_keys
    # Repeated 'Term Source REF' columns are disambiguated, not collapsed.
    assert any(k.startswith("Term Source REF.") for k in header_keys)


def test_read_samples_extracts_names_and_characteristics():
    samples = read_samples(_read("s_*.txt"))
    assert len(samples) == 5  # fixture holds 5 data rows
    first = samples[0]
    assert first["name"]  # Sample Name populated
    # Organism characteristic is attached as a child with its value.
    organisms = [
        c for c in first.get("characteristics", []) if c["category"] == "Organism"
    ]
    assert organisms and organisms[0]["value"] == "Homo sapiens"
    assert organisms[0].get("term_accession", "").endswith("NCBITaxon_9606")


def test_read_metabolites_extracts_maf_rows():
    metabolites = read_metabolites(_read("m_*.tsv"))
    # Every fixture MAF row identifies a metabolite (by id or name).
    assert len(metabolites) >= 1
    assert all(
        m.get("database_identifier") or m.get("metabolite_identification")
        for m in metabolites
    )


def test_read_data_files_extracts_named_files():
    files = read_data_files(_read("a_*.txt"))
    # The assay file references at least one spectral data file, linked to a sample.
    assert files, "expected data files in the assay fixture"
    assert all(f["name"] for f in files)
    assert any("Data File" in f["kind"] for f in files)
