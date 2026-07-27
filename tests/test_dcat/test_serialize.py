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


# --- provenance: derived from, not identical to --------------------------


def _published_card():
    """A card describing a dataset derived from an ENA record."""
    from metaseed.dcat.model import DcatDataset

    return DcatDataset(
        identifier="https://example.org/d/1",
        title="Derived dataset",
        source=["https://www.ebi.ac.uk/ena/browser/view/PRJEB12345"],
        is_version_of="https://www.ebi.ac.uk/ena/browser/view/PRJEB12345",
        version="2",
        conforms_to=["https://www.miappe.org/"],
    )


def test_one_source_emits_both_dct_source_and_prov_was_derived_from():
    """The two predicates state the same fact for different readers, so they
    must point at the same object rather than drift apart."""
    from metaseed.dcat.serialize import PROV

    graph = to_graph(_published_card())
    node = next(graph.subjects(RDF.type, DCAT.Dataset))

    sources = set(graph.objects(node, DCTERMS.source))
    derived = set(graph.objects(node, PROV.wasDerivedFrom))
    assert sources == derived
    assert str(next(iter(sources))).endswith("PRJEB12345")


def test_is_version_of_is_a_reference_not_a_string():
    graph = to_graph(_published_card())
    node = next(graph.subjects(RDF.type, DCAT.Dataset))

    from metaseed.dcat.serialize import DCAT3

    value = graph.value(node, DCTERMS.isVersionOf)
    assert isinstance(value, rdflib.URIRef), "a URL must serialize as a reference"
    assert str(graph.value(node, DCAT3.version)) == "2"


def test_conforms_to_names_the_standard():
    graph = to_graph(_published_card())
    node = next(graph.subjects(RDF.type, DCAT.Dataset))

    assert str(graph.value(node, DCTERMS.conformsTo)) == "https://www.miappe.org/"


def test_a_card_carries_exactly_one_identifier():
    """Guards the regression this work exists to prevent: a card that also
    claims the origin's identifier asserts two identities for one record."""
    graph = to_graph(_published_card())
    node = next(graph.subjects(RDF.type, DCAT.Dataset))

    identifiers = list(graph.objects(node, DCTERMS.identifier))
    assert [str(i) for i in identifiers] == ["https://example.org/d/1"]


def test_the_provenance_survives_a_jsonld_round_trip():
    """An unbound prov namespace would silently drop or mangle the triple."""
    from metaseed.dcat.serialize import PROV

    parsed = rdflib.Graph().parse(data=to_jsonld(_published_card()), format="json-ld")

    assert any(parsed.triples((None, PROV.wasDerivedFrom, None)))
    assert len(parsed) == len(to_graph(_published_card()))


def test_a_catalog_publisher_uri_is_honoured_like_a_dataset_publisher():
    """The catalog used to mint a blank node even when given a URI, so the same
    publisher appeared as two different subjects depending on where it sat."""
    from metaseed.dcat.model import DcatAgent, DcatDataset

    agent = DcatAgent(name="Example Org", uri="https://example.org/org")
    cat = build_dcat_catalog(title="c", datasets=[DcatDataset(identifier="d1")])
    cat.publisher = agent

    graph = to_graph(cat)
    node = next(graph.subjects(RDF.type, DCAT.Catalog))

    assert graph.value(node, DCTERMS.publisher) == rdflib.URIRef(
        "https://example.org/org"
    )
