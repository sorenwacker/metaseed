"""A published release states its creators, the release before it and its status.

metaseed-hub publishes dataset releases; these are the DCAT terms a release
record needs beyond a single publication (docs/architecture/dcat.md).
"""

from __future__ import annotations

import pytest

rdflib = pytest.importorskip("rdflib")

from metaseed.dcat import (  # noqa: E402
    ADMS_STATUS,
    DcatAgent,
    DcatDataset,
    PublicationContext,
    build_published_dataset,
)
from metaseed.dcat.serialize import to_graph  # noqa: E402

from .test_shacl_conformance import _validate  # noqa: E402

DCAT = rdflib.Namespace("http://www.w3.org/ns/dcat#")
DCT = rdflib.Namespace("http://purl.org/dc/terms/")
ADMS = rdflib.Namespace("http://www.w3.org/ns/adms#")
FOAF = rdflib.Namespace("http://xmlns.com/foaf/0.1/")
RELEASE_2 = "https://hub.example.org/hub/releases/r2"
RELEASE_3 = "https://hub.example.org/hub/releases/r3"


def _release(status: str = "completed") -> DcatDataset:
    card = DcatDataset(
        title="Wheat drought trial", description="A field trial under drought stress."
    )
    return build_published_dataset(
        card,
        PublicationContext(
            landing_page=RELEASE_3,
            license="CC-BY-4.0",
            version="3",
            previous_version=RELEASE_2,
            creators=[
                DcatAgent(
                    name="Ada Example", uri="https://orcid.org/0000-0000-0000-0000"
                ),
                DcatAgent(name="Ben Example"),
            ],
            status=status,
        ),
    )


def _subject(graph: rdflib.Graph) -> rdflib.term.Node:
    return next(graph.subjects(rdflib.RDF.type, DCAT.Dataset))


def test_a_release_names_its_creators_in_order_given() -> None:
    graph = to_graph(_release())
    names = {
        str(graph.value(creator, FOAF.name))
        for creator in graph.objects(_subject(graph), DCT.creator)
    }
    assert names == {"Ada Example", "Ben Example"}
    assert (
        rdflib.URIRef("https://orcid.org/0000-0000-0000-0000"),
        FOAF.name,
        rdflib.Literal("Ada Example"),
    ) in graph


def test_a_release_links_the_release_before_it() -> None:
    graph = to_graph(_release())
    assert graph.value(_subject(graph), DCAT.previousVersion) == rdflib.URIRef(
        RELEASE_2
    )


def test_a_withdrawn_release_says_so() -> None:
    graph = to_graph(_release(status="withdrawn"))
    assert graph.value(_subject(graph), ADMS.status) == rdflib.URIRef(
        ADMS_STATUS["withdrawn"]
    )


def test_an_unknown_status_is_refused() -> None:
    with pytest.raises(ValueError, match="status"):
        PublicationContext(landing_page=RELEASE_3, status="retracted")


def test_a_release_record_conforms_to_dcat_ap() -> None:
    conforms, _report, report_text = _validate(to_graph(_release(status="withdrawn")))
    assert conforms, f"the release record violates DCAT-AP shapes:\n{report_text}"
