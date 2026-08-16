"""The publication seam is published on purpose, so it is gated (260816 review).

The 260816 review found `metaseed.dcat.publication` had no caller anywhere in
metaseed or metaseed-hub and flagged it as dead. It is not: it is exported from
`metaseed.dcat` and documented in docs/architecture/dcat.md as how a publishing
platform supplies what metaseed deliberately does not model — where a dataset
can be fetched, what identifies it there, and what may be done with it.

Reusability by other applications is an aim of this library, so "no caller in
this repository" is the expected state for such a seam, not evidence against
it. Deleting it would have been invisible to every gate here and broken a
downstream at import. This test is the missing evidence: it pins the exported
names and the shape the documentation promises, so the seam reads as supported
rather than as an oversight.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("rdflib")

from metaseed import dcat

#: What docs/architecture/dcat.md tells a publisher to import.
DOCUMENTED = ("PublicationContext", "build_published_dataset", "origin_url")


def test_the_documented_names_are_exported() -> None:
    for name in DOCUMENTED:
        assert hasattr(dcat, name), f"{name} is documented but not exported"
        assert name in dcat.__all__, f"{name} is exported but not in __all__"


def test_the_documentation_still_describes_this_seam() -> None:
    """If the docs stop naming it, the seam is no longer promised to anyone."""
    page = (
        Path(__file__).resolve().parents[2] / "docs" / "architecture" / "dcat.md"
    ).read_text()

    assert "metaseed.dcat.publication" in page
    for name in DOCUMENTED:
        assert name in page, f"{name} is exported but no longer documented"
