"""A loaded entity exists once, not embedded in its parent and again as a node.

`_load_children` materialised every embedded child as its own node but left the
embedded object in the parent's containment field, so the store held each
entity below the root twice. This is the load path behind `load_yaml` and every
shipped example, so any save or export after loading one emitted duplicated
data.

It also made deletion look impossible to fix: `delete_entity` removed the node
and unlinked the reference, but the parent's copy of the whole record stayed
behind and was re-emitted by `to_dict` and every exporter. The duplicate is the
cause, so it is fixed here rather than taught to the unlink path.

The link between parent and child travels through the child's parent-reference
field (`investigation_id`), which `EntityStore.add_entity` fills; a containment
field that merely restates the child is not a second link, it is a second copy.
A field entry that NAMES a child (a plain string) is a reference and is kept.
"""

from __future__ import annotations

from metaseed.facade import ProfileFacade


def _entities(facade: ProfileFacade) -> list[dict]:
    return facade.to_dict()


def _of_type(facade: ProfileFacade, entity_type: str) -> list[dict]:
    return [e for e in _entities(facade) if e.get("_type") == entity_type]


def _nested_document() -> dict:
    return {
        "unique_id": "INV-1",
        "title": "I",
        "studies": [{"unique_id": "ST-1", "title": "S"}],
    }


def test_a_child_is_not_also_embedded_in_its_parent() -> None:
    facade = ProfileFacade("miappe", "1.2")
    facade.load_nested(_nested_document())

    investigation = _of_type(facade, "Investigation")[0]

    assert not any(
        isinstance(item, dict) for item in investigation.get("studies", [])
    ), f"the Study is stored twice: {investigation.get('studies')}"


def test_every_entity_appears_exactly_once() -> None:
    facade = ProfileFacade("miappe", "1.2")
    facade.load_nested(_nested_document())

    identifiers = [e.get("unique_id") for e in _entities(facade)]

    assert sorted(identifiers) == ["INV-1", "ST-1"]


def test_deleting_a_child_removes_the_record_entirely() -> None:
    """The delete finding, which the duplicate made unfixable at the unlink."""
    facade = ProfileFacade("miappe", "1.2")
    facade.load_nested(_nested_document())
    study_node = _of_type(facade, "Study")[0]["_node_id"]

    facade.delete_entity(study_node)

    remaining = _entities(facade)
    assert len(remaining) == 1, f"the Study survived deletion: {remaining}"
    investigation = remaining[0]
    assert not investigation.get("studies"), (
        f"the deleted Study is still inside its parent: {investigation.get('studies')}"
    )


def test_a_named_child_is_a_reference_and_is_kept() -> None:
    """A plain string names a child; only an embedded object is a copy."""
    facade = ProfileFacade("miappe", "1.2")
    facade.load_nested(
        {"unique_id": "INV-1", "title": "I", "studies": ["ST-ELSEWHERE"]}
    )

    investigation = _of_type(facade, "Investigation")[0]

    assert investigation.get("studies") == ["ST-ELSEWHERE"]


def test_a_mixed_field_keeps_its_names_and_loads_its_objects() -> None:
    facade = ProfileFacade("miappe", "1.2")
    facade.load_nested(
        {
            "unique_id": "INV-1",
            "title": "I",
            "studies": ["ST-ELSEWHERE", {"unique_id": "ST-1", "title": "S"}],
        }
    )

    investigation = _of_type(facade, "Investigation")[0]

    assert investigation.get("studies") == ["ST-ELSEWHERE"]
    assert [e["unique_id"] for e in _of_type(facade, "Study")] == ["ST-1"]


def test_a_shipped_example_loads_each_entity_once() -> None:
    """The path that matters: every shipped example goes through load_yaml."""
    from metaseed.facade.documents import read_yaml
    from metaseed.paths import get_builtin_specs_dir

    examples = sorted(
        (get_builtin_specs_dir().parent / "examples" / "miappe" / "1.2").glob("*.yaml")
    )
    if not examples:
        import pytest

        pytest.skip("no shipped miappe 1.2 example to load")

    facade = ProfileFacade("miappe", "1.2")
    facade.load_nested(read_yaml(examples[0]))

    embedded = [
        (e.get("_type"), field)
        for e in _entities(facade)
        for field, value in e.items()
        if isinstance(value, list) and any(isinstance(v, dict) for v in value)
    ]
    assert not embedded, f"entities embedded in their parents: {embedded}"
