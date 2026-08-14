"""`to_graph` draws every declared reference, and says which restate containment.

Issue #251: a `type: list` reference (MIAPPE's `Event.observation_unit_ids`)
produced no edge at all — the one link a containment tree genuinely cannot
show, since the members live elsewhere in the tree. And a reference that runs
parallel to containment (`Study.investigation_id` beside the Study being a
child of that Investigation) was drawn indistinguishably from one that adds
information, with no way for a consumer to tell them apart without
re-deriving containment itself.
"""

from __future__ import annotations

import pytest

from metaseed.facade import ProfileFacade


@pytest.fixture
def facade_with_event() -> ProfileFacade:
    facade = ProfileFacade("miappe", "1.1")
    inv = facade.add_entity("Investigation", {"unique_id": "INV-1", "title": "T"})
    study = facade.add_entity(
        "Study",
        {"unique_id": "STU-1", "title": "S"},
        parent_id=inv.id,
    )
    facade.add_entity(
        "ObservationUnit",
        {"unique_id": "OU-1", "observation_unit_type": "plant", "study_id": "STU-1"},
        parent_id=study.id,
    )
    facade.add_entity(
        "Event",
        {
            "unique_id": "EV-1",
            "event_type": "watering",
            "study_id": "STU-1",
            "observation_unit_ids": ["OU-1"],
        },
        parent_id=study.id,
    )
    return facade


def _graph(facade: ProfileFacade) -> dict:
    return facade.to_graph()


def test_a_list_valued_reference_produces_one_edge_per_member(
    facade_with_event: ProfileFacade,
) -> None:
    graph = _graph(facade_with_event)

    labels = [e.get("label") for e in graph["edges"] if e.get("label")]
    assert "observation_unit_ids" in labels, labels


def test_a_reference_parallel_to_containment_is_flagged(
    facade_with_event: ProfileFacade,
) -> None:
    graph = _graph(facade_with_event)

    by_label = {}
    for edge in graph["edges"]:
        if edge.get("label"):
            by_label.setdefault(edge["label"], []).append(edge)

    # A child's study_id restates the child being nested under that Study:
    # the edge stays (it IS declared) but says so.
    assert all(e.get("redundant") for e in by_label["study_id"])
    # The Event's unit reference adds information containment cannot show.
    assert all(not e.get("redundant") for e in by_label["observation_unit_ids"])
