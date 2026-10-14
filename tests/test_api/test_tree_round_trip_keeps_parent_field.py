"""A tree serialize/load round trip keeps which field holds each child.

The tree format wrote no parent_field, so a SEEK Person filed under a Study's
experimentalists came back under whichever Person field matched first.
"""

from metaseed.api import MetaseedClient


def _client_with_experimentalist() -> MetaseedClient:
    client = MetaseedClient("seek", "1.0")
    facade = client.facade
    investigation = facade.add_entity(
        "Investigation", {"identifier": "INV-1", "title": "I"}, skip_validation=True
    )
    study = facade.add_entity(
        "Study",
        {"identifier": "STU-1", "title": "S"},
        parent_id=investigation.id,
        skip_validation=True,
    )
    facade.add_entity(
        "Person",
        {"identifier": "P-1", "first_name": "Ada", "last_name": "Example"},
        parent_id=study.id,
        parent_field="experimentalists",
        skip_validation=True,
    )
    return client


def test_tree_serialization_records_the_parent_field() -> None:
    tree = _client_with_experimentalist().serialize(format="tree")["tree"]

    person = tree[0]["children"][0]["children"][0]
    assert person["entity_type"] == "Person"
    assert person["parent_field"] == "experimentalists"


def test_tree_round_trip_keeps_the_parent_field() -> None:
    payload = _client_with_experimentalist().serialize(format="tree")

    reloaded = MetaseedClient("seek", "1.0")
    reloaded.load(payload)

    (investigation,) = reloaded.facade.get_roots()
    (study,) = investigation.children
    assert [(p.entity_type, p.parent_field) for p in study.children] == [
        ("Person", "experimentalists")
    ]
