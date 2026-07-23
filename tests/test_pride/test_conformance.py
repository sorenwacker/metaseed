"""Conformance of the PRIDE ``submission.px`` export to the px-submission format.

Structural validation: PRIDE has no external schema (unlike ENA's SRA XSD), so
this asserts the px-submission-tool structure — the required ``MTD`` metadata
lines and a well-formed ``FMH``/``FME`` file-mapping section. Opt-in (network):
exports a real project and checks the result would be structurally accepted.
"""

from __future__ import annotations

import pytest

from metaseed.pride import import_accession, to_pride_submission

# MTD keys the px-submission tool requires for a project.
_REQUIRED_MTD = (
    "project_title",
    "project_description",
    "submitter_name",
    "submitter_email",
    "submission_type",
)


def _px_violations(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln]
    mtd = {
        parts[1]
        for ln in lines
        if (parts := ln.split("\t"))[0] == "MTD" and len(parts) >= 3
    }
    errors = [f"missing MTD {k}" for k in _REQUIRED_MTD if k not in mtd]
    if "species" not in mtd:
        errors.append("no species line")
    if "instrument" not in mtd:
        errors.append("no instrument line")

    if not any(ln.startswith("FMH\t") for ln in lines):
        errors.append("missing FMH header")
    fme = [ln for ln in lines if ln.startswith("FME\t")]
    if not fme:
        errors.append("no FME file entries")
    for ln in fme:
        cols = ln.split("\t")
        if len(cols) != 4:
            errors.append(f"FME has {len(cols)} columns, expected 4: {ln!r}")
        elif not cols[1].isdigit():
            errors.append(f"FME file_id not numeric: {ln!r}")
    return errors


@pytest.mark.network
def test_pride_export_is_px_conformant():
    px = to_pride_submission(import_accession("PXD000001"))["submission.px"]
    assert _px_violations(px) == []
