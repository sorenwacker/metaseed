"""Tests for tree-format loading (issue #209).

Two behaviors are pinned here: a child stays attached to its parent even when the
parent carries no stored ``id``, and a permissive load reports every node it
drops instead of aborting the whole dataset.
"""

from __future__ import annotations

from typing import Any

import pytest

from metaseed import MetaseedClient, SkippedNode


@pytest.fixture
def client() -> MetaseedClient:
    """A client for a profile with an Investigation -> Study hierarchy."""
    return MetaseedClient("miappe", "1.1")


def _node(entity_type: str, title: str, *children: Any, **extra: Any) -> dict[str, Any]:
    """Build a tree payload node without a stored ``id``."""
    return {
        "entity_type": entity_type,
        "data": {"title": title},
        "children": list(children),
        **extra,
    }


class TestParentLinkage:
    """Children stay under their parent regardless of stored ids."""

    def test_child_of_node_without_id_is_not_flattened_to_a_root(
        self, client: MetaseedClient
    ) -> None:
        payload = {"tree": [_node("Investigation", "T", _node("Study", "S"))]}

        client.load(payload)

        roots = client.facade.get_roots()
        assert [r.entity_type for r in roots] == ["Investigation"]
        assert [c.entity_type for c in roots[0].children] == ["Study"]

    def test_grandchild_of_nodes_without_ids_keeps_its_depth(
        self, client: MetaseedClient
    ) -> None:
        payload = {
            "tree": [
                _node(
                    "Investigation",
                    "T",
                    _node("Study", "S", _node("ObservationUnit", "O")),
                )
            ]
        }

        client.load(payload)

        roots = client.facade.get_roots()
        assert len(roots) == 1
        study = roots[0].children[0]
        assert [c.entity_type for c in study.children] == ["ObservationUnit"]

    def test_stored_ids_are_preserved(self, client: MetaseedClient) -> None:
        payload = {
            "tree": [
                _node("Investigation", "T", _node("Study", "S", id="s1"), id="inv1")
            ]
        }

        client.load(payload)

        roots = client.facade.get_roots()
        assert roots[0].id == "inv1"
        assert roots[0].children[0].id == "s1"


class TestStrictLoadIsTheDefault:
    """Without ``on_skip`` the loader behaves exactly as before."""

    def test_unknown_entity_type_raises(self, client: MetaseedClient) -> None:
        payload = {"tree": [_node("NotAThing", "T")]}

        with pytest.raises(KeyError, match="NotAThing"):
            client.load(payload)

    def test_missing_entity_type_raises(self, client: MetaseedClient) -> None:
        payload = {"tree": [{"data": {"title": "T"}, "children": []}]}

        with pytest.raises(KeyError):
            client.load(payload)


class TestPermissiveLoad:
    """``on_skip`` enables permissive loading and receives every dropped node."""

    def test_unknown_entity_type_is_skipped_not_raised(
        self, client: MetaseedClient
    ) -> None:
        payload = {
            "tree": [
                _node("NotAThing", "bad"),
                _node("Investigation", "good"),
            ]
        }
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 1
        assert [r.entity_type for r in client.facade.get_roots()] == ["Investigation"]
        assert len(skipped) == 1
        assert skipped[0].entity_type == "NotAThing"
        assert "NotAThing" in skipped[0].reason

    def test_missing_entity_type_is_reported_with_no_type(
        self, client: MetaseedClient
    ) -> None:
        payload = {"tree": [{"data": {"title": "T"}, "children": []}]}
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 0
        assert len(skipped) == 1
        assert skipped[0].entity_type is None
        assert "entity_type" in skipped[0].reason

    def test_skipped_node_takes_its_subtree_and_reports_the_count(
        self, client: MetaseedClient
    ) -> None:
        payload = {
            "tree": [
                _node(
                    "NotAThing",
                    "bad",
                    _node("Study", "S", _node("ObservationUnit", "O")),
                )
            ]
        }
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 0
        assert client.facade.get_roots() == []
        assert len(skipped) == 1
        assert skipped[0].descendants_dropped == 2

    def test_orphans_are_not_re_parented(self, client: MetaseedClient) -> None:
        """A dropped node's children must not be promoted under its parent."""
        payload = {
            "tree": [
                _node(
                    "Investigation",
                    "T",
                    _node("NotAThing", "bad", _node("Study", "S")),
                )
            ]
        }
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 1
        roots = client.facade.get_roots()
        assert roots[0].children == []
        assert client.facade.list_entities("Study") == []
        assert len(skipped) == 1

    def test_skipped_payload_node_is_available_for_recovery(
        self, client: MetaseedClient
    ) -> None:
        bad = _node("NotAThing", "bad", _node("Study", "S"))
        skipped: list[SkippedNode] = []

        client.load({"tree": [bad]}, on_skip=skipped.append)

        assert skipped[0].node is bad
        assert skipped[0].node["children"][0]["entity_type"] == "Study"

    def test_non_mapping_node_is_skipped(self, client: MetaseedClient) -> None:
        payload = {"tree": ["not a node", _node("Investigation", "good")]}
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 1
        assert len(skipped) == 1
        assert skipped[0].entity_type is None

    def test_malformed_children_is_reported_and_the_node_still_loads(
        self, client: MetaseedClient
    ) -> None:
        payload = {
            "tree": [
                {
                    "entity_type": "Investigation",
                    "data": {"title": "T"},
                    "children": "not a list",
                }
            ]
        }
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 1
        assert len(skipped) == 1
        assert "children" in skipped[0].reason

    def test_malformed_tree_is_reported(self, client: MetaseedClient) -> None:
        skipped: list[SkippedNode] = []

        loaded = client.load({"tree": "not a list"}, on_skip=skipped.append)

        assert loaded == 0
        assert len(skipped) == 1
        assert "tree" in skipped[0].reason

    def test_clean_payload_reports_nothing(self, client: MetaseedClient) -> None:
        payload = {"tree": [_node("Investigation", "T", _node("Study", "S"))]}
        skipped: list[SkippedNode] = []

        loaded = client.load(payload, on_skip=skipped.append)

        assert loaded == 2
        assert skipped == []

    def test_node_without_id_still_keeps_its_children(
        self, client: MetaseedClient
    ) -> None:
        """The hub's other workaround: permissive load must not need stored ids."""
        payload = {"tree": [_node("Investigation", "T", _node("Study", "S"))]}
        skipped: list[SkippedNode] = []

        client.load(payload, on_skip=skipped.append)

        roots = client.facade.get_roots()
        assert len(roots) == 1
        assert [c.entity_type for c in roots[0].children] == ["Study"]


class TestAMalformedPayloadCannotWipeTheStore:
    """A dict with neither "tree" nor "entities" must refuse, not clear.

    The fallthrough `data if isinstance(data, list) else []` turned a typo'd
    key ({"entitles": ...}), a wrong shape, or a truncated file into an empty
    list, and load_from_dict clears the store before loading — so a malformed
    payload silently destroyed every existing entity and returned 0.
    """

    def test_a_typoed_key_raises_and_keeps_the_data(
        self, client: MetaseedClient
    ) -> None:
        client.create_entity("Investigation", {"title": "Keep me"})

        with pytest.raises(ValueError, match=r"tree|entities"):
            client.load({"entitles": [{"_type": "Investigation"}]})

        assert len(client.get_roots()) == 1

    def test_a_bare_list_still_loads(self, client: MetaseedClient) -> None:
        loaded = client.load([{"_type": "Investigation", "title": "T"}])

        assert loaded == 1
