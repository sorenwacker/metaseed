"""Serialize the DCAT model to RDF (JSON-LD / Turtle).

Targets **DCAT 3** (the current W3C Recommendation). DCAT 2 and 3 share the
``http://www.w3.org/ns/dcat#`` namespace, so this is a question of which terms
are used, not of which IRI: see :data:`DCAT3`.

This is the only DCAT module that depends on ``rdflib``; it is imported lazily
(never from ``metaseed.dcat.__init__``) so the model and resolver remain usable
without the ``metaseed[dcat]`` extra installed.

See docs/architecture/dcat.md and issue #28.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import quote

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
        DcatAgent,
        DcatCatalog,
        DcatContactPoint,
        DcatDataset,
        DcatDistribution,
    )

VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
PROV = Namespace("http://www.w3.org/ns/prov#")
DCAT3 = Namespace(str(DCAT))
"""The DCAT namespace, unvalidated, for terms newer than rdflib knows.

rdflib 7.6 ships ``DCAT`` as a closed list of 36 DCAT 2 terms: reaching
``DCAT.version`` (or ``DatasetSeries``, ``inSeries``, ``previousVersion``)
through it emits a spurious "not defined in namespace" warning even though
the term is valid DCAT 3. Same namespace IRI, so the emitted RDF is identical
either way; this just stops a correct term from looking like a typo.
"""
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
    "prov": str(PROV),
}


# Characters that may not appear in an IRI (rdflib refuses to serialize these).
_INVALID_IRI = re.compile(r"""[\s<>"{}|\\^`]""")


def _iri_ok(value: str) -> bool:
    """Whether ``value`` is usable as an IRI (no whitespace or illegal chars)."""
    return bool(value) and _INVALID_IRI.search(value) is None


def _safe_uriref(value: str) -> Node:
    """A URIRef when ``value`` is a usable IRI, otherwise a plain literal."""
    return URIRef(value) if _iri_ok(value) else Literal(value)


def _node_for(identifier: str | None) -> Node:
    """A stable node IRI for a dataset/catalog, or a blank node if none.

    Identifiers that are already valid IRIs are used as-is; anything else is
    minted under ``urn:metaseed:`` with the local part percent-encoded, so a
    value such as ``"My Dataset 2024"`` still serializes to valid RDF.
    """
    if not identifier:
        return BNode()
    if ("://" in identifier or identifier.startswith("urn:")) and _iri_ok(identifier):
        return URIRef(identifier)
    return _BASE[quote(identifier, safe="-._~")]


def _uri_or_literal(value: str) -> Node:
    """Render a value as a URIRef when it is a usable IRI, else a literal."""
    return URIRef(value) if "://" in value and _iri_ok(value) else Literal(value)


def _add_agent(graph: Graph, agent: DcatAgent) -> Node:
    """Add a ``foaf:Agent`` node and return it.

    Shared by dataset and catalog publishers so the two cannot drift: the
    catalog previously always minted a blank node, discarding a publisher URI
    the dataset would have honoured.
    """
    uri = agent.uri
    node = URIRef(uri) if uri and _iri_ok(uri) else BNode()
    graph.add((node, RDF.type, FOAF.Agent))
    if agent.name:
        graph.add((node, FOAF.name, Literal(agent.name)))
    if agent.email:
        graph.add((node, FOAF.mbox, Literal(agent.email)))
    return node


def _add_contact(graph: Graph, contact: DcatContactPoint) -> Node:
    node = BNode()
    graph.add((node, RDF.type, VCARD.Kind))
    if contact.name:
        graph.add((node, VCARD.fn, Literal(contact.name)))
    if contact.email:
        mailto = f"mailto:{contact.email}"
        graph.add(
            (
                node,
                VCARD.hasEmail,
                URIRef(mailto) if _iri_ok(mailto) else Literal(contact.email),
            )
        )
    return node


def _add_distribution(graph: Graph, dist: DcatDistribution) -> Node:
    node = BNode()
    graph.add((node, RDF.type, DCAT.Distribution))
    if dist.title:
        graph.add((node, DCTERMS.title, Literal(dist.title)))
    if dist.access_url:
        graph.add((node, DCAT.accessURL, _safe_uriref(dist.access_url)))
    if dist.download_url:
        graph.add((node, DCAT.downloadURL, _safe_uriref(dist.download_url)))
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


def _add_provenance(graph: Graph, node: Node, dataset: DcatDataset) -> None:
    """Emit where this dataset came from and which version it is."""
    if dataset.version:
        graph.add((node, DCAT3.version, Literal(dataset.version)))
    if dataset.is_version_of:
        graph.add((node, DCTERMS.isVersionOf, _uri_or_literal(dataset.is_version_of)))
    for origin in dataset.source:
        # Both predicates, one object: dct:source is the DCAT-AP reader's term
        # and prov:wasDerivedFrom the provenance reader's, for the same fact.
        origin_node = _uri_or_literal(origin)
        graph.add((node, DCTERMS.source, origin_node))
        graph.add((node, PROV.wasDerivedFrom, origin_node))
    for standard in dataset.conforms_to:
        graph.add((node, DCTERMS.conformsTo, _uri_or_literal(standard)))


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
        graph.add((node, DCAT.landingPage, _safe_uriref(dataset.landing_page)))
    for keyword in dataset.keywords:
        graph.add((node, DCAT.keyword, Literal(keyword)))
    for theme in dataset.themes:
        graph.add((node, DCAT.theme, _uri_or_literal(theme)))
    for relation in dataset.related:
        graph.add((node, DCTERMS.relation, _uri_or_literal(relation)))
    _add_provenance(graph, node, dataset)
    if dataset.publisher and dataset.publisher.name:
        graph.add((node, DCTERMS.publisher, _add_agent(graph, dataset.publisher)))
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
        graph.add((node, FOAF.homepage, _safe_uriref(catalog.homepage)))
    if catalog.publisher and catalog.publisher.name:
        graph.add((node, DCTERMS.publisher, _add_agent(graph, catalog.publisher)))
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
    graph.bind("prov", PROV)
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
