"""An unmapped entity must not take its descendants with it (#260816 review)."""

from __future__ import annotations

from rdflib import RDF, Graph, Namespace

from metaseed import MetaseedClient
from metaseed.seek.fairds import to_fair_data_station_rdf

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")


def _tree_with_an_unmapped_middle() -> MetaseedClient:
    """Investigation -> Process (no JERM class) -> Study -> Sample."""
    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "INV1", "title": "I"}, skip_validation=True
    )
    process = client.create_entity(
        "Process", {"identifier": "PROC1"}, parent_id=inv.id, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU1", "title": "S"},
        parent_id=process.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample",
        {"identifier": "SAM1", "name": "Sample one"},
        parent_id=study.id,
        skip_validation=True,
    )
    return client


def _graph() -> Graph:
    g = Graph()
    g.parse(
        data=to_fair_data_station_rdf(_tree_with_an_unmapped_middle()), format="turtle"
    )
    return g


def test_descendants_of_an_unmapped_entity_are_still_exported() -> None:
    graph = _graph()

    studies = list(graph.subjects(RDF.type, JERM.Study))
    assert studies, "the Study below an unmapped Process was dropped"


def test_the_surfaced_subtree_stays_attached_to_the_nearest_mapped_ancestor() -> None:
    graph = _graph()

    inv = next(graph.subjects(RDF.type, JERM.Investigation))
    parts = set(graph.objects(inv, JERM.hasPart))
    study = next(graph.subjects(RDF.type, JERM.Study))
    assert study in parts, "the Study is exported but orphaned in the graph"


def test_the_unmapped_entity_itself_is_not_exported() -> None:
    """Skipping it is right; only taking its children along was wrong."""
    graph = _graph()

    identifiers = {
        str(o) for o in graph.objects(None, Namespace("http://schema.org/").identifier)
    }
    assert "PROC1" not in identifiers
