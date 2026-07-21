"""Tests for the FAIR Data Station Turtle RDF generator.

Hermetic — builds a small ISA dataset and parses the emitted Turtle back with
rdflib (no SEEK / network). SEEK's own reader accepts this format (verified
manually against a live instance).
"""

from __future__ import annotations

from rdflib import RDF, RDFS, Graph, Namespace

from metaseed import MetaseedClient
from metaseed.seek.fairds import to_fair_data_station_rdf

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")
SCHEMA = Namespace("http://schema.org/")


def _dataset() -> MetaseedClient:
    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "My Investigation", "description": "d"},
        skip_validation=True,
    )
    client.create_entity(
        "Study",
        # 'filename' is a non-core field -> exercises the property-definition path.
        {"identifier": "STU1", "title": "Study one", "filename": "s_study.txt"},
        parent_id=inv.id,
        skip_validation=True,
    )
    return client


def _graph() -> Graph:
    graph = Graph()
    graph.parse(data=to_fair_data_station_rdf(_dataset()), format="turtle")
    return graph


def test_investigation_typed_and_titled():
    graph = _graph()
    inv = next(graph.subjects(RDF.type, JERM.Investigation))
    assert (inv, SCHEMA.identifier, None) in graph
    assert str(next(graph.objects(inv, SCHEMA.title))) == "My Investigation"


def test_hierarchy_via_haspart():
    graph = _graph()
    inv = next(graph.subjects(RDF.type, JERM.Investigation))
    study = next(graph.objects(inv, JERM.hasPart))
    assert (study, RDF.type, JERM.Study) in graph


def test_field_property_definitions_carry_label_and_required():
    graph = _graph()
    # every schema property used as a predicate on a resource is declared with a
    # label + valueRequired so SEEK can build an Extended Metadata attribute.
    props = set(graph.subjects(RDF.type, RDF.Property))
    assert props  # at least one non-core field was emitted with a definition
    for prop in props:
        assert (prop, RDFS.label, None) in graph
        assert (prop, SCHEMA.valueRequired, None) in graph
