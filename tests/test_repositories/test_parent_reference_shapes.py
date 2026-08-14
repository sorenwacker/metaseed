"""`update_parent_reference` must respect the field's declared shape.

`nested_fields` includes both LIST and ENTITY (exactly-one-child) fields, and
the helper unconditionally treated the target as a list: an ENTITY-typed
reference was rewritten from a scalar into a list — a shape the models never
validate (entity fields are typed Any) — and a second child was appended to a
field the profile declares holds exactly one.
"""

from __future__ import annotations

from metaseed.facade import ProfileFacade
from metaseed.repositories.helpers import update_parent_reference


def test_an_entity_typed_reference_stays_scalar() -> None:
    facade = ProfileFacade("seek", "1.0")
    parent_data: dict = {}

    field = update_parent_reference(
        facade=facade,
        parent_data=parent_data,
        parent_type="Study",
        child_data={"name": "Dr. One"},
        child_type="Person",
        child_id="node-1",
    )

    assert field == "person_responsible"
    assert isinstance(parent_data["person_responsible"], str)


def test_a_second_child_does_not_stack_onto_an_exactly_one_field() -> None:
    facade = ProfileFacade("seek", "1.0")
    parent_data: dict = {}

    for name, node in (("Dr. One", "n1"), ("Dr. Two", "n2")):
        update_parent_reference(
            facade=facade,
            parent_data=parent_data,
            parent_type="Study",
            child_data={"name": name},
            child_type="Person",
            child_id=node,
        )
        if node == "n1":
            first_ref = parent_data["person_responsible"]

    assert parent_data["person_responsible"] == first_ref


def test_a_list_typed_reference_still_appends() -> None:
    facade = ProfileFacade("miappe", "1.1")
    parent_data: dict = {}

    for uid, node in (("S1", "n1"), ("S2", "n2")):
        update_parent_reference(
            facade=facade,
            parent_data=parent_data,
            parent_type="Investigation",
            child_data={"unique_id": uid, "title": uid},
            child_type="Study",
            child_id=node,
        )

    assert parent_data["studies"] == ["S1", "S2"]
