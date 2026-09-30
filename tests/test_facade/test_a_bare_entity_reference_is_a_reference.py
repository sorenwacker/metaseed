"""A reference naming only an entity is a reference like any other.

``EntityHelper.reference_fields`` kept only ``Entity.field`` references, so a
field declared ``reference: Source`` -- the form template-bound profiles use
for every ``Input`` list, whose values are predecessors' titles -- was invisible
to the dataset graph and the editor's pickers. The CropXR phenotyping example
rendered as containment only: no edge from an observation unit to its source.
"""

from __future__ import annotations

from metaseed import MetaseedClient

SPEC = {
    "version": "1.0",
    "name": "bare_reference_probe",
    "root_entity": "Study",
    "entities": {
        "Study": {
            "fields": [
                {
                    "name": "study_id",
                    "type": "string",
                    "required": True,
                    "is_identifier": True,
                },
                {"name": "sources", "type": "list", "items": "Source"},
                {"name": "units", "type": "list", "items": "Unit"},
            ]
        },
        "Source": {
            "fields": [
                {
                    "name": "Source Name",
                    "type": "string",
                    "required": True,
                    "is_identifier": True,
                },
            ]
        },
        "Unit": {
            "fields": [
                {
                    "name": "unit_id",
                    "type": "string",
                    "required": True,
                    "is_identifier": True,
                },
                {
                    "name": "Input",
                    "type": "list",
                    "items": "string",
                    "reference": "Source",
                },
                {"name": "study_ref", "type": "string", "reference": "Study.study_id"},
            ]
        },
    },
}


def _client() -> MetaseedClient:
    client = MetaseedClient.from_spec(SPEC)
    study = client.create_entity("Study", {"study_id": "S1"})
    for name in ("Col-0-control", "Col-0-drought"):
        client.create_entity("Source", {"Source Name": name}, parent_id=study.id)
    client.create_entity(
        "Unit",
        {
            "unit_id": "U1",
            "Input": ["Col-0-control", "Col-0-drought"],
            "study_ref": "S1",
        },
        parent_id=study.id,
    )
    return client


def test_a_bare_entity_reference_names_the_targets_identifier() -> None:
    client = _client()

    assert client.facade.Unit.reference_fields == {
        "Input": ("Source", "Source Name"),
        "study_ref": ("Study", "study_id"),
    }


def test_the_graph_draws_one_edge_per_input_member() -> None:
    graph = _client().facade.to_graph()
    types = {n["id"]: n.get("group") for n in graph["nodes"]}

    inputs = [e for e in graph["edges"] if e.get("label") == "Input"]

    assert [(types[e["from"]], types[e["to"]]) for e in inputs] == [
        ("Unit", "Source")
    ] * 2
    assert all(e.get("dashes") and not e.get("redundant") for e in inputs)


def test_a_field_qualified_reference_is_unchanged() -> None:
    graph = _client().facade.to_graph()

    assert [e for e in graph["edges"] if e.get("label") == "study_ref"], "still drawn"
