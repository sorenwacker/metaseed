"""A reference that names only an entity resolves against that entity's identifier.

Template-bound profiles (CropXR) declare their ``Input`` lists as
``reference: Source`` -- the entity, no field -- and the values are the
predecessors' titles, the field each entity marks ``is_identifier``. The
dataset validator registered only ``unique_id`` values and the fields named
by ``Entity.field`` targets, so every such reference came back
``Reference not found``: 88 false reports on the CropXR phenotyping example,
none of them wrong data. ``check`` had the gap already; ``validate()`` running
the same pass made it reach every user.
"""

from __future__ import annotations

from metaseed import MetaseedClient

SPEC = {
    "version": "1.0",
    "name": "input_reference_probe",
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
            ]
        },
    },
}


def _study() -> tuple[MetaseedClient, str]:
    client = MetaseedClient.from_spec(SPEC)
    study = client.create_entity("Study", {"study_id": "S1"})
    client.create_entity("Source", {"Source Name": "Col-0-control"}, parent_id=study.id)
    return client, study.id


def _broken(client: MetaseedClient) -> list[tuple[str | None, str]]:
    return [
        (i.entity_id, i.field)
        for i in client.validate().issues
        if i.rule == "reference_integrity"
    ]


def test_an_input_naming_an_existing_source_by_title_resolves() -> None:
    client, study_id = _study()
    client.create_entity(
        "Unit", {"unit_id": "U1", "Input": ["Col-0-control"]}, parent_id=study_id
    )

    assert _broken(client) == []


def test_an_input_naming_no_source_is_reported() -> None:
    client, study_id = _study()
    unit = client.create_entity(
        "Unit", {"unit_id": "U1", "Input": ["Col-0-missing"]}, parent_id=study_id
    )

    assert _broken(client) == [(unit.id, "Input")]


def test_a_field_qualified_target_still_resolves_by_that_field() -> None:
    client = MetaseedClient("miappe", "1.2")
    inv = client.create_entity("Investigation", {"unique_id": "INV-1", "title": "T"})
    study = client.create_entity(
        "Study",
        {"unique_id": "STU-1", "investigation_id": "INV-1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "ObservationUnit",
        {"unique_id": "OU-1", "study_id": "STU-1"},
        parent_id=study.id,
        skip_validation=True,
    )

    assert _broken(client) == []
