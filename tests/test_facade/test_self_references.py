"""An entity type whose reference field names its own type.

Darwin Core is full of these — ``parentEventID`` names another Event,
``acceptedNameUsageID`` and ``parentNameUsageID`` name another Taxon — and no
shipped profile has declared one before, so the store's reference-based
parenting has never been exercised this way.

It matters because a reference here does not merely record a link: it decides
the parent. A chain must therefore build a hierarchy, and a cycle must not
leave a dataset with no roots at all — every node having a parent — nor a
``children`` graph that recurses without end.
"""

from __future__ import annotations

import pytest

from metaseed.facade import ProfileFacade


@pytest.fixture
def facade():
    """A profile whose Event references another Event."""
    from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType, ProfileSpec

    event = EntityDefSpec(
        fields=[
            FieldSpec(name="eventID", type=FieldType.STRING, required=True),
            FieldSpec(
                name="parentEventID",
                type=FieldType.STRING,
                reference="Event.eventID",
            ),
        ],
    )
    spec = ProfileSpec(
        name="selfref", version="1.0", root_entity="Event", entities={"Event": event}
    )
    return ProfileFacade("selfref", "1.0", spec=spec)


def _load(facade, rows):
    return facade.load_from_dict([{"_type": "Event", **row} for row in rows])


class TestAChainBuildsAHierarchy:
    def test_a_child_is_parented_under_the_event_it_names(self, facade) -> None:
        _load(
            facade,
            [{"eventID": "E1"}, {"eventID": "E2", "parentEventID": "E1"}],
        )

        roots = facade.get_roots()

        assert [r.instance.eventID for r in roots] == ["E1"]
        assert len(facade.get_children(roots[0].id)) == 1

    def test_a_three_deep_chain_keeps_one_root(self, facade) -> None:
        _load(
            facade,
            [
                {"eventID": "E1"},
                {"eventID": "E2", "parentEventID": "E1"},
                {"eventID": "E3", "parentEventID": "E2"},
            ],
        )

        assert len(facade.get_roots()) == 1


class TestACycleIsRefused:
    def test_two_events_naming_each_other_leave_a_root(self, facade) -> None:
        """The failure this prevents: every node parented, so the dataset reads
        as empty — the same silent zero that hid the example-loading bug."""
        _load(
            facade,
            [
                {"eventID": "E1", "parentEventID": "E2"},
                {"eventID": "E2", "parentEventID": "E1"},
            ],
        )

        assert facade.get_roots(), "a cycle left the dataset with no roots"

    def test_the_children_graph_stays_walkable(self, facade) -> None:
        _load(
            facade,
            [
                {"eventID": "E1", "parentEventID": "E2"},
                {"eventID": "E2", "parentEventID": "E1"},
            ],
        )

        seen, stack = set(), list(facade.get_roots())
        while stack:
            node = stack.pop()
            assert node.id not in seen, "the walk revisited a node: the graph loops"
            seen.add(node.id)
            stack.extend(facade.get_children(node.id))

        assert len(seen) == 2

    def test_an_event_naming_itself_is_not_its_own_parent(self, facade) -> None:
        _load(facade, [{"eventID": "E1", "parentEventID": "E1"}])

        roots = facade.get_roots()

        assert len(roots) == 1
        assert roots[0].parent_id is None

    def test_a_longer_cycle_is_refused_too(self, facade) -> None:
        _load(
            facade,
            [
                {"eventID": "E1", "parentEventID": "E3"},
                {"eventID": "E2", "parentEventID": "E1"},
                {"eventID": "E3", "parentEventID": "E2"},
            ],
        )

        assert facade.get_roots()
