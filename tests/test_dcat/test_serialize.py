"""Tests for DCAT RDF serialization (#28).

Parse the emitted RDF back with rdflib and assert the expected triples, rather
than string-matching the serialization.
"""

from __future__ import annotations

import pytest

from metaseed.dcat import build_dcat_catalog, build_dcat_dataset
from metaseed.dcat.model import DcatChecksum, DcatDistribution
from metaseed.repositories.dataset_repository import CatalogMetadata

rdflib = pytest.importorskip("rdflib")
from rdflib.namespace import DCAT, DCTERMS, RDF  # noqa: E402

from metaseed.dcat.serialize import to_graph, to_jsonld, to_turtle  # noqa: E402


def test_dataset_triples_present():
    from metaseed.specs.schema import FieldSpec, FieldType

    fields = [
        FieldSpec(name="title", type=FieldType.STRING, dcat="dct:title"),
        FieldSpec(name="submission_date", type=FieldType.DATE, dcat="dct:issued"),
        FieldSpec(name="license", type=FieldType.URI, dcat="dct:license"),
    ]
    root = {
        "title": "Drought trial",
        "submission_date": "2024-01-01",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }
    ds = build_dcat_dataset(root_fields=fields, root_entity=root)
    graph = to_graph(ds)

    subjects = list(graph.subjects(RDF.type, DCAT.Dataset))
    assert len(subjects) == 1
    node = subjects[0]
    assert str(graph.value(node, DCTERMS.title)) == "Drought trial"
    assert str(graph.value(node, DCTERMS.issued)) == "2024-01-01"
    # license is an IRI, not a literal
    assert isinstance(graph.value(node, DCTERMS.license), rdflib.URIRef)


def test_catalog_links_datasets():
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="d1")
    cat = build_dcat_catalog(title="Cat", publisher="Org", datasets=[ds])
    graph = to_graph(cat)

    catalogs = list(graph.subjects(RDF.type, DCAT.Catalog))
    assert len(catalogs) == 1
    assert len(list(graph.objects(catalogs[0], DCAT.dataset))) == 1


def test_distribution_and_checksum():
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="d1")
    ds.distributions = [
        DcatDistribution(
            download_url="https://example.org/d1.ttl",
            media_type="text/turtle",
            byte_size=42,
            checksum=DcatChecksum(algorithm="SHA-256", value="abc"),
        )
    ]
    graph = to_graph(ds)
    dists = list(graph.subjects(RDF.type, DCAT.Distribution))
    assert len(dists) == 1
    assert int(graph.value(dists[0], DCAT.byteSize)) == 42


def test_turtle_and_jsonld_are_nonempty_strings():
    cm = CatalogMetadata(title="t", description="d", publisher="p")
    ds = build_dcat_dataset(root_fields=[], catalog_metadata=cm)
    cat = build_dcat_catalog(title="c", datasets=[ds])

    turtle = to_turtle(cat)
    jsonld = to_jsonld(cat)
    assert "dcat:Catalog" in turtle
    assert "@context" in jsonld
    # JSON-LD parses back to the same triple count
    assert len(to_graph(cat)) == len(
        rdflib.Graph().parse(data=jsonld, format="json-ld")
    )
