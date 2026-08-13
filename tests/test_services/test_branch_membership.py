"""`within` decides what a value may be, not only what a picker offers (#229).

`ontologies:` says which ontology a value comes from. It cannot say *which part*
of one, so a column meant for a technology type accepted any term in the
ontology, and a profile built from a single domain ontology could not
distinguish its columns at all. `within` names the branch — and until now it
narrowed the picker while validation kept accepting anything from the ontology,
which is a rule that exists in the specification and nowhere in the enforcement.

The third outcome carries the weight here. Whether a term sits beneath another
is a question only a hierarchy can answer: a flat local vocabulary cannot, and a
service that will not respond has not said no. Both must report *not checked*,
because reporting "outside the branch" would turn a gap in what we know into a
fault in someone's data.
"""

from __future__ import annotations

from metaseed.services.term_check import Outcome, check_term


class _Hierarchy:
    """A source that knows one branch: TO:0001 sits under TO:0000."""

    def __init__(self, **answers: bool | None) -> None:
        self.answers = answers
        self.asked: list[tuple[str, str]] = []

    def get_term_sync(self, term_id: str) -> object | None:
        return object()

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return True

    def is_within_sync(self, term_id: str, ancestor: str) -> bool | None:
        self.asked.append((term_id, ancestor))
        return self.answers.get(term_id, False)


class _NoHierarchy:
    """A flat vocabulary: it has the terms, but no notion of beneath."""

    def get_term_sync(self, term_id: str) -> object | None:
        return object()

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return True


class TestAValueInsideTheBranch:
    def test_it_passes(self) -> None:
        source = _Hierarchy(**{"TO:0001": True})

        verdict = check_term("TO:0001", ["to"], source, within="TO:0000")

        assert verdict.outcome is Outcome.OK
        assert source.asked == [("TO:0001", "TO:0000")]

    def test_the_branch_is_only_asked_about_once_the_term_exists(self) -> None:
        """No point asking where a term sits when it is not a term at all."""

        class _Missing(_Hierarchy):
            def get_term_sync(self, term_id: str) -> object | None:
                return None

        source = _Missing()

        verdict = check_term("TO:0404", ["to"], source, within="TO:0000")

        assert verdict.outcome is Outcome.NOT_FOUND
        assert source.asked == []


class TestAValueOutsideTheBranch:
    def test_it_is_reported(self) -> None:
        source = _Hierarchy(**{"TO:0002": False})

        verdict = check_term("TO:0002", ["to"], source, within="TO:0000")

        assert verdict.outcome is Outcome.NOT_IN_BRANCH
        assert verdict.is_problem
        assert "TO:0000" in (verdict.message or "")

    def test_it_says_which_branch_the_field_wanted(self) -> None:
        verdict = check_term(
            "TO:0002", ["to"], _Hierarchy(**{"TO:0002": False}), within="TO:0000"
        )

        assert "TO:0002" in (verdict.message or "")


class TestWhenNobodyCanSay:
    def test_a_source_with_no_hierarchy_reports_not_checked(self) -> None:
        """A flat vocabulary file has no parents to walk. Silence would pass the
        value off as verified against a branch nobody looked at."""
        verdict = check_term("TO:0002", ["to"], _NoHierarchy(), within="TO:0000")

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem
        assert "TO:0000" in (verdict.message or "")

    def test_a_source_that_answers_none_reports_not_checked(self) -> None:
        verdict = check_term(
            "TO:0002", ["to"], _Hierarchy(**{"TO:0002": None}), within="TO:0000"
        )

        assert verdict.outcome is Outcome.NOT_CHECKED

    def test_an_outage_reports_not_checked(self) -> None:
        class _Down(_NoHierarchy):
            def is_within_sync(self, term_id: str, ancestor: str) -> bool | None:
                raise ConnectionError("EBI is down")

        verdict = check_term("TO:0002", ["to"], _Down(), within="TO:0000")

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem


class TestWhenNoBranchIsDeclared:
    def test_nothing_is_asked(self) -> None:
        source = _Hierarchy()

        verdict = check_term("TO:0002", ["to"], source)

        assert verdict.outcome is Outcome.OK
        assert source.asked == []
