"""Conformance of the MetaboLights export to the ISA-Tab structure.

Structural validation (ISA-Tab has no installable schema here): the investigation
file must carry the required ISA sections, and the bundle must include the study,
assay, and MAF files with their mandatory headers. Opt-in (network).
"""

from __future__ import annotations

import pytest

from metaseed.metabolights import import_accession, to_metabolights

_REQUIRED_SECTIONS = (
    "ONTOLOGY SOURCE REFERENCE",
    "INVESTIGATION",
    "STUDY",
    "STUDY FACTORS",
    "STUDY ASSAYS",
    "STUDY PROTOCOLS",
    "STUDY CONTACTS",
)


def _isatab_violations(docs: dict[str, str]) -> list[str]:
    errors = []
    inv = docs.get("i_Investigation.txt", "")
    errors += [f"missing section {s}" for s in _REQUIRED_SECTIONS if s not in inv]
    if "Investigation Identifier" not in inv:
        errors.append("no Investigation Identifier row")

    # Each table must exist AND carry at least one data row. A header-only file is
    # the #146 false positive: the importer emitted empty s_/a_/m_ tables and this
    # check certified them as valid, hiding total sample/metabolite data loss.
    for prefix, label in (("s_", "study"), ("a_", "assay"), ("m_", "MAF")):
        matched = [n for n in docs if n.startswith(prefix)]
        if not matched:
            errors.append(f"no {label} ({prefix}) file")
        for name in matched:
            if len(docs[name].splitlines()) <= 1:
                errors.append(f"{name} has no data rows (header only)")

    # Mandatory headers on each table (a_ and m_, not only s_).
    for name in (n for n in docs if n.startswith(("s_", "a_"))):
        if "Sample Name" not in docs[name].splitlines()[0]:
            errors.append(f"{name} missing 'Sample Name' header")
    for name in (n for n in docs if n.startswith("m_")):
        header = docs[name].splitlines()[0] if docs[name].splitlines() else ""
        if "metabolite_identification" not in header:
            errors.append(f"{name} missing 'metabolite_identification' header")
    return errors


def test_isatab_violations_rejects_header_only_bundle():
    # Network-free proof that the gate now fails a header-only export (the exact
    # false positive #96 allowed before #146).
    header_only = {
        "i_Investigation.txt": "\n".join(
            [*(f"{s}\nInvestigation Identifier\tX" for s in _REQUIRED_SECTIONS)]
        ),
        "s_MTBLS.txt": "Source Name\tSample Name\n",  # header only
        "a_MTBLS.txt": "Sample Name\tRaw Spectral Data File\n",  # header only
        "m_MTBLS.tsv": "database_identifier\tmetabolite_identification\n",  # header only
    }
    violations = _isatab_violations(header_only)
    assert any("header only" in v for v in violations), violations


@pytest.mark.network
def test_metabolights_export_is_isatab_conformant():
    docs = to_metabolights(import_accession("MTBLS1"))
    assert _isatab_violations(docs) == []
