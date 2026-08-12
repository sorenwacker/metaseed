"""The document loader, tested without a facade.

That it can be is the point of separating it: it needs somewhere to put
entities and a way to ask what may nest inside what, and those three questions
are the whole of its dependency. Before, the same walk was four methods on a
thirty-eight-method class and could only be exercised through the whole of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metaseed.facade.documents import DocumentLoader, is_serialized


@dataclass
class _Node:
    id: str


@dataclass
class _Helper:
    nested_fields: dict[str, str] = field(default_factory=dict)
    owned_child_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class _Sink:
    """A list with the three methods the loader asks for."""

    helpers: dict[str, _Helper]
    ownership: bool = False
    added: list[tuple[str, str | None, dict[str, Any]]] = field(default_factory=list)

    def add_entity(
        self,
        entity_type: str,
        data: dict[str, Any],
        node_id: str | None = None,
        parent_id: str | None = None,
        skip_validation: bool = False,
    ) -> _Node:
        self.added.append((entity_type, parent_id, data))
        return _Node(id=f"n{len(self.added)}")

    def get_helper(self, entity_type: str) -> _Helper | None:
        return self.helpers.get(entity_type)

    def uses_ownership(self) -> bool:
        return self.ownership


def _sink(ownership: bool = False) -> _Sink:
    return _Sink(
        helpers={
            "Investigation": _Helper(
                nested_fields={"studies": "Study", "contacts": "Contact"},
                owned_child_fields={"studies": "Study"},
            ),
            "Study": _Helper(nested_fields={"observations": "Observation"}),
            "Observation": _Helper(),
            "Contact": _Helper(),
        },
        ownership=ownership,
    )


DOCUMENT = {
    "unique_id": "INV-1",
    "studies": [
        {"unique_id": "STU-1", "observations": [{"unique_id": "OBS-1"}]},
    ],
    "contacts": [{"name": "A. Person"}],
}


class TestWalkingADocument:
    def test_every_level_is_loaded(self) -> None:
        sink = _sink()

        loaded = DocumentLoader(sink, "Investigation").load(DOCUMENT)

        assert loaded == 4
        assert [t for t, _, _ in sink.added] == [
            "Investigation",
            "Study",
            "Observation",
            "Contact",
        ]

    def test_each_child_is_added_under_its_parent(self) -> None:
        sink = _sink()

        DocumentLoader(sink, "Investigation").load(DOCUMENT)

        parents = {t: p for t, p, _ in sink.added}
        assert parents["Investigation"] is None
        assert parents["Study"] == "n1"
        assert parents["Observation"] == "n2", "a grandchild hangs from its own parent"

    def test_ownership_markers_decide_what_becomes_an_entity(self) -> None:
        """With markers, a nested field nobody owns stays inline.

        Here Investigation owns only ``studies``, and Study marks nothing at
        all — which a profile using markers is entitled to say, and which means
        Study has no tree children. So the Contact *and* the Observation stay
        embedded, and two entities are loaded rather than four.
        """
        sink = _sink(ownership=True)

        loaded = DocumentLoader(sink, "Investigation").load(DOCUMENT)

        assert loaded == 2
        assert [t for t, _, _ in sink.added] == ["Investigation", "Study"]

    def test_a_string_is_a_reference_not_a_child(self) -> None:
        sink = _sink()

        loaded = DocumentLoader(sink, "Investigation").load(
            {"unique_id": "INV-1", "studies": ["STU-1"]}
        )

        assert loaded == 1

    def test_an_unknown_root_loads_nothing(self) -> None:
        sink = _sink()

        assert DocumentLoader(sink, None).load({"unique_id": "X"}) == 0

    def test_a_type_the_profile_does_not_define_is_skipped(self) -> None:
        sink = _sink()
        sink.helpers["Investigation"].nested_fields["ghosts"] = "Ghost"

        loaded = DocumentLoader(sink, "Investigation").load(
            {"unique_id": "INV-1", "ghosts": [{"unique_id": "G-1"}]}
        )

        assert loaded == 1


class TestTellingTheFormatsApart:
    def test_a_serialized_entity_is_recognised_by_its_type_key(self) -> None:
        assert is_serialized([{"_type": "Investigation", "unique_id": "INV-1"}])

    def test_a_document_carries_no_type_key(self) -> None:
        assert not is_serialized([{"unique_id": "INV-1", "studies": []}])

    def test_one_typed_entity_is_enough(self) -> None:
        """A serialized payload is uniform; a single marker settles it."""
        assert is_serialized([{"unique_id": "a"}, {"_type": "Study"}])
