"""The DCAT export conforms to the DCAT-AP SHACL shapes (#29).

The shapes are vendored (tests/test_dcat/shapes/dcat-ap.shapes.ttl, from
SEMICeu/dcat-ap_shacl master, the 2.x shape set — pinned by vendoring, so a
shapes migration is a deliberate re-vendor, not a silent behavior change)
and validation runs offline through pySHACL. A deliberately broken graph
must report violations, or a passing report proves nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pyshacl = pytest.importorskip("pyshacl")
rdflib = pytest.importorskip("rdflib")

from metaseed import MetaseedClient  # noqa: E402
from metaseed.dcat.export import to_dcat  # noqa: E402

SHAPES = Path(__file__).parent / "shapes" / "dcat-ap.shapes.ttl"


def _sample_export() -> rdflib.Graph:
    client = MetaseedClient("miappe", "1.2")
    client.create_entity(
        "Investigation",
        {
            "unique_id": "INV-1",
            "title": "Wheat drought trial",
            "description": "A field trial under drought stress.",
            "license": "https://creativecommons.org/licenses/by/4.0/",
        },
        skip_validation=True,
    )
    files = to_dcat(client)
    graph = rdflib.Graph()
    graph.parse(data=files["dcat.ttl"], format="turtle")
    return graph


def _validate(graph: rdflib.Graph):
    shapes = rdflib.Graph()
    shapes.parse(SHAPES, format="turtle")
    # The shape set uses implicit class targeting: a shape targets its own
    # URI's instances only when that URI is ALSO an rdfs:Class in the shapes
    # graph. The class declarations come from owl:imports the offline run
    # cannot resolve, so they are supplied directly — without them nothing
    # is targeted and every graph "conforms".
    DCAT = rdflib.Namespace("http://www.w3.org/ns/dcat#")
    for cls in (DCAT.Dataset, DCAT.Distribution, DCAT.Catalog):
        shapes.add((cls, rdflib.RDF.type, rdflib.RDFS.Class))
    return pyshacl.validate(graph, shacl_graph=shapes, advanced=True)


def test_a_sample_export_conforms() -> None:
    conforms, _report_graph, report_text = _validate(_sample_export())
    assert conforms, f"the DCAT export violates DCAT-AP shapes:\n{report_text}"


def test_a_broken_graph_is_reported() -> None:
    """dcat:byteSize must be a decimal; a string violates the shape.

    Without this the conformance test could pass because nothing was
    checked at all.
    """
    graph = _sample_export()
    dataset = next(
        graph.subjects(
            rdflib.RDF.type, rdflib.URIRef("http://www.w3.org/ns/dcat#Dataset")
        )
    )
    distribution = rdflib.URIRef("urn:test:distribution")
    DCAT = rdflib.Namespace("http://www.w3.org/ns/dcat#")
    graph.add((dataset, DCAT.distribution, distribution))
    graph.add((distribution, rdflib.RDF.type, DCAT.Distribution))
    graph.add((distribution, DCAT.byteSize, rdflib.Literal("not a number")))

    conforms, _report_graph, report_text = _validate(graph)
    assert not conforms, "a wrong-typed byteSize must be a reported violation"
    assert "byteSize" in report_text
