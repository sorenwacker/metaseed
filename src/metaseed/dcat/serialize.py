"""Serialize the DCAT model to RDF (JSON-LD / Turtle).

This is the only DCAT module that depends on ``rdflib``; it is imported lazily
(never from ``metaseed.dcat.__init__``) so the model and resolver remain usable
without the ``metaseed[dcat]`` extra installed.

See docs/architecture/dcat.md and issue #28.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from rdflib import BNode, Graph, Literal, Namespace, URIRef
    from rdflib.namespace import DCAT, DCTERMS, FOAF, RDF
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "DCAT serialization requires rdflib. Install with: pip install 'metaseed[dcat]'"
    ) from exc

if TYPE_CHECKING:
    from rdflib.term import Node

    from metaseed.dcat.model import (
        DcatCatalog,
        DcatContactPoint,
        DcatDataset,
        DcatDistribution,
    )

VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
SPDX = Namespace("http://spdx.org/rdf/terms#")
_BASE = Namespace("urn:metaseed:")

# Minimal JSON-LD context — only the vocabularies the card actually uses, so the
# output is not padded with rdflib's full default namespace registry.
_JSONLD_CONTEXT: dict[str, str] = {
    "dcat": str(DCAT),
    "dct": str(DCTERMS),
    "foaf": str(FOAF),
    "vcard": str(VCARD),
    "spdx": str(SPDX),
}


def _node_for(identifier: str | None) -> Node:
    """A URIRef from the identifier, or a blank node if there is none."""
    if not identifier:
        return BNode()
    if "://" in identifier or identifier.startswith("urn:"):
        return URIRef(identifier)
    return _BASE[identifier]


def _uri_or_literal(value: str) -> Node:
    """Render a value as a URIRef when it looks like an IRI, else a literal."""
    return URIRef(value) if "://" in value else Literal(value)


def _add_contact(graph: Graph, contact: DcatContactPoint) -> Node:
    node = BNode()
    graph.add((node, RDF.type, VCARD.Kind))
    if contact.name:
        graph.add((node, VCARD.fn, Literal(contact.name)))
    if contact.email:
        graph.add((node, VCARD.hasEmail, URIRef(f"mailto:{contact.email}")))
    return node


def _add_distribution(graph: Graph, dist: DcatDistribution) -> Node:
    node = BNode()
    graph.add((node, RDF.type, DCAT.Distribution))
    if dist.title:
        graph.add((node, DCTERMS.title, Literal(dist.title)))
    if dist.access_url:
        graph.add((node, DCAT.accessURL, URIRef(dist.access_url)))
    if dist.download_url:
        graph.add((node, DCAT.downloadURL, URIRef(dist.download_url)))
    if dist.media_type:
        graph.add((node, DCAT.mediaType, Literal(dist.media_type)))
    if dist.format:
        graph.add((node, DCTERMS["format"], Literal(dist.format)))
    if dist.byte_size is not None:
        graph.add((node, DCAT.byteSize, Literal(dist.byte_size)))
    if dist.license:
        graph.add((node, DCTERMS.license, _uri_or_literal(dist.license)))
    if dist.checksum:
        cs = BNode()
        graph.add((cs, RDF.type, SPDX.Checksum))
        graph.add((cs, SPDX.algorithm, Literal(dist.checksum.algorithm)))
        graph.add((cs, SPDX.checksumValue, Literal(dist.checksum.value)))
        graph.add((node, SPDX.checksum, cs))
    return node


def _add_dataset(graph: Graph, dataset: DcatDataset) -> Node:
    node = _node_for(dataset.identifier)
    graph.add((node, RDF.type, DCAT.Dataset))
    if dataset.identifier:
        graph.add((node, DCTERMS.identifier, Literal(dataset.identifier)))
    if dataset.title:
        graph.add((node, DCTERMS.title, Literal(dataset.title)))
    if dataset.description:
        graph.add((node, DCTERMS.description, Literal(dataset.description)))
    if dataset.issued:
        graph.add((node, DCTERMS.issued, Literal(dataset.issued)))
    if dataset.modified:
        graph.add((node, DCTERMS.modified, Literal(dataset.modified)))
    if dataset.license:
        graph.add((node, DCTERMS.license, _uri_or_literal(dataset.license)))
    if dataset.access_rights:
        graph.add((node, DCTERMS.accessRights, Literal(dataset.access_rights)))
    if dataset.landing_page:
        graph.add((node, DCAT.landingPage, URIRef(dataset.landing_page)))
    for keyword in dataset.keywords:
        graph.add((node, DCAT.keyword, Literal(keyword)))
    for theme in dataset.themes:
        graph.add((node, DCAT.theme, _uri_or_literal(theme)))
    for relation in dataset.related:
        graph.add((node, DCTERMS.relation, _uri_or_literal(relation)))
    if dataset.publisher and dataset.publisher.name:
        pub = URIRef(dataset.publisher.uri) if dataset.publisher.uri else BNode()
        graph.add((pub, RDF.type, FOAF.Agent))
        graph.add((pub, FOAF.name, Literal(dataset.publisher.name)))
        graph.add((node, DCTERMS.publisher, pub))
    if dataset.contact_point:
        graph.add((node, DCAT.contactPoint, _add_contact(graph, dataset.contact_point)))
    for dist in dataset.distributions:
        graph.add((node, DCAT.distribution, _add_distribution(graph, dist)))
    return node


def _add_catalog(graph: Graph, catalog: DcatCatalog) -> Node:
    node = _node_for(catalog.identifier)
    graph.add((node, RDF.type, DCAT.Catalog))
    if catalog.title:
        graph.add((node, DCTERMS.title, Literal(catalog.title)))
    if catalog.description:
        graph.add((node, DCTERMS.description, Literal(catalog.description)))
    if catalog.homepage:
        graph.add((node, FOAF.homepage, URIRef(catalog.homepage)))
    if catalog.publisher and catalog.publisher.name:
        pub = BNode()
        graph.add((pub, RDF.type, FOAF.Agent))
        graph.add((pub, FOAF.name, Literal(catalog.publisher.name)))
        graph.add((node, DCTERMS.publisher, pub))
    for dataset in catalog.datasets:
        graph.add((node, DCAT.dataset, _add_dataset(graph, dataset)))
    return node


def to_graph(obj: DcatCatalog | DcatDataset) -> Graph:
    """Build an RDF graph for a :class:`DcatCatalog` or :class:`DcatDataset`."""
    from metaseed.dcat.model import DcatCatalog

    graph = Graph()
    graph.bind("dcat", DCAT)
    graph.bind("dct", DCTERMS)
    graph.bind("foaf", FOAF)
    graph.bind("vcard", VCARD)
    if isinstance(obj, DcatCatalog):
        _add_catalog(graph, obj)
    else:
        _add_dataset(graph, obj)
    return graph


def to_turtle(obj: DcatCatalog | DcatDataset) -> str:
    """Serialize to Turtle."""
    return to_graph(obj).serialize(format="turtle")


def to_jsonld(obj: DcatCatalog | DcatDataset) -> str:
    """Serialize to JSON-LD with a minimal, card-specific @context."""
    return to_graph(obj).serialize(format="json-ld", context=_JSONLD_CONTEXT)
