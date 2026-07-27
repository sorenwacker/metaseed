"""The DCAT card as an export any host can offer.

DCAT is the one adapter whose output is meaningful for every profile, and it was
the only registered adapter with no actions at all — so no host offered it and
the card was unreachable outside metaseed's own ``/dcat`` page.
"""

from __future__ import annotations

import pytest

from metaseed import MetaseedClient, adapters
from metaseed.specs.loader import SpecLoader

rdflib = pytest.importorskip("rdflib")

from metaseed.dcat.export import to_dcat  # noqa: E402


def _client() -> MetaseedClient:
    client = MetaseedClient("pride", "1.0")
    client.create_entity(
        "Dataset",
        {
            "identifier": "local-1",
            "accession": "PXD000001",
            "title": "TMT spikes in Erwinia",
            "description": "A proteomics submission used as a fixture.",
            "keywords": ["proteomics"],
        },
        skip_validation=True,
    )
    return client


def test_the_card_is_emitted_in_both_serializations() -> None:
    files = to_dcat(_client())

    assert set(files) == {"dcat.jsonld", "dcat.ttl"}
    turtle = rdflib.Graph().parse(data=files["dcat.ttl"], format="turtle")
    jsonld = rdflib.Graph().parse(data=files["dcat.jsonld"], format="json-ld")
    assert len(turtle) == len(jsonld), "the two serializations must agree"
    assert len(turtle) > 0


def test_the_card_carries_the_dataset_s_own_metadata() -> None:
    """A card whose title came out empty is not consumable by anything."""
    from rdflib.namespace import DCAT, DCTERMS, RDF

    graph = rdflib.Graph().parse(data=to_dcat(_client())["dcat.ttl"], format="turtle")
    node = next(graph.subjects(RDF.type, DCAT.Dataset))

    assert str(graph.value(node, DCTERMS.title)) == "TMT spikes in Erwinia"
    assert str(graph.value(node, DCTERMS.source)) == "PXD000001"
    assert str(graph.value(node, DCTERMS.identifier)) == "local-1"


def test_a_card_is_one_dataset_not_a_catalog() -> None:
    """A consumer asking for this dataset's record should get a record, not a
    ``@graph`` of a catalogue wrapping it."""
    import json

    from rdflib.namespace import DCAT, RDF

    files = to_dcat(_client())
    graph = rdflib.Graph().parse(data=files["dcat.ttl"], format="turtle")

    assert not list(graph.subjects(RDF.type, DCAT.Catalog))
    assert len(list(graph.subjects(RDF.type, DCAT.Dataset))) == 1
    assert json.loads(files["dcat.jsonld"]).get("@type") == "dcat:Dataset"


def test_an_empty_dataset_exports_nothing_rather_than_an_empty_card() -> None:
    """Hosts treat an empty mapping as "nothing to export" and say so; a card
    describing no dataset would download as a valid-looking but empty file."""
    assert to_dcat(MetaseedClient("pride", "1.0")) == {}


@pytest.mark.parametrize(
    "profile", [*SpecLoader().list_profiles(), "a-profile-that-does-not-exist"]
)
def test_the_export_is_offered_for_every_profile(profile: str) -> None:
    """DCAT describes any dataset, including one built in the Spec Builder,
    whose profile name cannot be known here."""
    keys = {a.key for a in adapters.actions_for_profile(profile, kind="export")}

    assert "dcat" in keys, f"{profile} is not offered the DCAT card"
