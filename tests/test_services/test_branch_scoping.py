"""A column can take one branch of an ontology, not just a whole ontology.

`ontologies: [po]` cannot tell a plant anatomical entity from any other Plant
Ontology term, and a profile built from one domain ontology — a JERM-derived
profile has ten such columns — cannot distinguish its columns at all: assay
type, technology type and four file-format columns are all "somewhere in JERM"
(#229).

`within` names the term whose descendants are the valid values. This narrows
the picker; whether it also constrains validation is deliberately a separate
decision, because rejecting values outside a branch would invalidate existing
datasets and needs its own measurement.
"""

from __future__ import annotations

from metaseed.services.terms import TermRouter


class _Branching:
    """A source that can restrict to a subtree, and records what it was asked."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, str | None]] = []

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return None

    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def search_sync(self, query, ontology=None, limit=20, within=None):
        self.calls.append((query, ontology, within))
        return [_Hit("JERM:00030", "microarray")] if within else [_Hit("JERM:1", "x")]


class _Flat:
    """A source with no hierarchy — a file of terms, say."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return None

    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def search_sync(self, query, ontology=None, limit=20):
        self.calls.append(query)
        return [_Hit("LOCAL:1", "anything at all")]


class _Hit:
    def __init__(self, term_id: str, label: str) -> None:
        self.id = term_id
        self.label = label
        self.ontology = None
        self.description = None


class TestScopingToABranch:
    def test_the_branch_reaches_the_source(self) -> None:
        source = _Branching()

        TermRouter([source]).search_sync("micro", "jerm", 20, within="JERM:00025")

        assert source.calls == [("micro", "jerm", "JERM:00025")]

    def test_without_a_branch_nothing_changes(self) -> None:
        source = _Branching()

        TermRouter([source]).search_sync("micro", "jerm", 20)

        assert source.calls == [("micro", "jerm", None)]

    def test_a_source_that_cannot_restrict_is_skipped_not_widened(self) -> None:
        """The failure this prevents: a column asking for one branch and being
        handed the whole ontology by a source that ignored the restriction."""
        flat = _Flat()

        hits = TermRouter([flat]).search_sync("x", None, 20, within="JERM:00025")

        assert hits == []
        assert flat.calls == [], "the flat source was asked anyway"

    def test_that_source_still_answers_unrestricted_queries(self) -> None:
        flat = _Flat()

        hits = TermRouter([flat]).search_sync("x", None, 20)

        assert [h.id for h in hits] == ["LOCAL:1"]
