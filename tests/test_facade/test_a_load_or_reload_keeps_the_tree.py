"""Loading must not destroy what it fails to replace, and links must survive.

Three defects on the load/save path, all found by the 260816 review:

- `_load_tree` cleared the store before validating anything, so in strict mode
  a malformed node aborted the load AFTER the caller's dataset was already
  gone. `load()` guards against exactly this for an empty payload and says so
  in a comment; the tree path then did it anyway.
- `to_dict` emitted a parent link only as `_parent_unique_id`, and only when
  the parent had an identifier VALUE. A parent without one — routine for the
  drafts the UI persists — round-tripped with all of its children orphaned,
  even though `_node_id` is written for every node precisely so identity
  survives.
- A `type: entity` nested field is written as a scalar by
  `linking.linked_reference_value`, but reload only read list values, so the
  parent-child direction came back INVERTED where such a field is also a
  declared reference (isa's `Process.executes_protocol`).
"""

from __future__ import annotations

import pytest

from metaseed import MetaseedClient
from metaseed.facade import ProfileFacade


def _roots(facade: ProfileFacade) -> list[tuple[str, int]]:
    return [
        (node["entity_type"], len(node.get("children", [])))
        for node in facade.get_tree()
    ]


def test_a_rejected_payload_leaves_the_existing_dataset_alone() -> None:
    """Strict mode aborts the load; it must not take the dataset with it."""
    client = MetaseedClient("miappe", "1.2")
    client.create_entity("Investigation", {"unique_id": "INV-1", "title": "Keep me"})

    with pytest.raises(KeyError):
        client.load({"profile": "miappe", "version": "1.2", "tree": [{"data": {}}]})

    remaining = [e.get("unique_id") for e in client.facade.to_dict()]
    assert "INV-1" in remaining, f"the existing dataset was wiped: {remaining}"


def test_a_child_survives_a_parent_that_has_no_identifier() -> None:
    facade = ProfileFacade("miappe", "1.2")
    parent = facade.add_entity(
        "Investigation", {"title": "no id"}, skip_validation=True
    )
    facade.add_entity(
        "Study", {"unique_id": "ST-1"}, parent_id=parent.id, skip_validation=True
    )

    reloaded = ProfileFacade("miappe", "1.2")
    reloaded.load_from_dict(facade.to_dict())

    assert _roots(reloaded) == [("Investigation", 1)], _roots(reloaded)


def test_an_owned_single_entity_field_keeps_its_direction() -> None:
    """isa's `Process.executes_protocol` is `type: entity`, `owns: true`."""
    facade = ProfileFacade("isa", "1.0")
    facade.load_from_dict(
        [
            {"_type": "Process", "name": "P1", "executes_protocol": "PROTO-1"},
            {"_type": "Protocol", "name": "PROTO-1"},
        ]
    )

    roots = _roots(facade)
    assert ("Protocol", 1) not in roots, f"the owned child became the parent: {roots}"


def test_the_identifier_link_is_preferred_over_the_node_id() -> None:
    """Both intents at once, so neither erodes.

    Parent links resolve by identifier — it survives a reload and reads
    sensibly in a hand-written payload — and `tests/test_ui/test_htmx.py`
    pins that. The node id appears only where there is no identifier to use,
    which is the case that was orphaning children.
    """
    facade = ProfileFacade("miappe", "1.2")
    identified = facade.add_entity(
        "Investigation",
        {"unique_id": "INV-1", "title": "has one"},
        skip_validation=True,
    )
    facade.add_entity(
        "Study", {"unique_id": "ST-1"}, parent_id=identified.id, skip_validation=True
    )
    anonymous = facade.add_entity(
        "Investigation", {"title": "has none"}, skip_validation=True
    )
    facade.add_entity(
        "Study", {"unique_id": "ST-2"}, parent_id=anonymous.id, skip_validation=True
    )

    by_id = {e.get("unique_id"): e for e in facade.to_dict()}

    assert by_id["ST-1"]["_parent_unique_id"] == "INV-1"
    assert "_parent_id" not in by_id["ST-1"]
    assert "_parent_unique_id" not in by_id["ST-2"]
    assert by_id["ST-2"]["_parent_id"] == anonymous.id
