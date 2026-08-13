"""Every JERM class name the exporter recognises must exist in JERM.

:data:`~metaseed.seek.roles.ANNOTATION_CLASSES` decides what an entity's own
annotation is allowed to name. Its keys were read from the ontology; without a
gate they would drift from it the moment someone adds a plausible-looking one —
which is exactly how `JERM:00021` came to be discussed as though JERM had
numeric accessions. It has none: all 294 of its classes are named.

Marked ``network`` because the check *is* the download. That makes it a release
gate rather than a per-push one, like the example-accession gate beside it: the
table changes rarely and CI minutes are a budget.

PPEO's ``observation_unit`` is deliberately excluded from the comparison — it is
not a JERM class, which is the point of the comment beside it in the table.
"""

from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET

import pytest

from metaseed.seek.roles import ANNOTATION_CLASSES, JERM_ONTOLOGY_URL

OWL = "{http://www.w3.org/2002/07/owl#}"

#: Names in the table that come from somewhere other than JERM, with where.
NON_JERM = {
    "observation_unit": "PPEO, the ontology SEEK types that level from",
    "ObservationUnit": "SEEK's own name for the resource",
}


@pytest.fixture(scope="module")
def jerm_classes() -> frozenset[str]:
    """The local names of every class declared in the JERM ontology."""
    with urllib.request.urlopen(JERM_ONTOLOGY_URL, timeout=30) as response:
        root = ET.fromstring(response.read())
    return frozenset(
        iri.lstrip("#")
        for element in root.iter(f"{OWL}Class")
        if (iri := element.get("IRI", "")).startswith("#")
    )


@pytest.mark.network
def test_every_recognised_class_is_a_real_one(jerm_classes: frozenset[str]) -> None:
    invented = {
        name
        for name in ANNOTATION_CLASSES
        if name not in NON_JERM and name not in jerm_classes
    }

    assert not invented, (
        f"not classes in JERM: {sorted(invented)}. Read the ontology at "
        f"{JERM_ONTOLOGY_URL} rather than adding a name that looks right."
    )


@pytest.mark.network
def test_jerm_has_no_numeric_accessions(jerm_classes: frozenset[str]) -> None:
    """So an annotation such as ``JERM:00021`` names nothing there, and mapping
    one to a class would be inventing an identifier rather than reading it."""
    accessions = {
        name
        for name in jerm_classes
        if name.isdigit() or name.removeprefix("JERM_").isdigit()
    }

    assert not accessions, f"JERM now has accession-style classes: {sorted(accessions)}"
