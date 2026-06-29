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
    if not [n for n in docs if n.startswith("s_")]:
        errors.append("no study (s_) file")
    if not [n for n in docs if n.startswith("a_")]:
        errors.append("no assay (a_) file")
    if not [n for n in docs if n.startswith("m_")]:
        errors.append("no MAF (m_) file")
    for name in (n for n in docs if n.startswith("s_")):
        if "Sample Name" not in docs[name].splitlines()[0]:
            errors.append(f"{name} missing 'Sample Name' header")
    return errors


@pytest.mark.network
def test_metabolights_export_is_isatab_conformant():
    docs = to_metabolights(import_accession("MTBLS1"))
    assert _isatab_violations(docs) == []
