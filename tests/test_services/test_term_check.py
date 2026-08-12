"""A value is checked against the ontology its field names.

A profile could already say a field takes a term from `to` or `co_321`, and
nothing read it: the check asked OLS whether the term existed anywhere, so a
phenotype term passed a field demanding a trait term (issue #215).

Nothing here touches the network. The service is a protocol, and these tests
pass a stand-in, because a check about what an answer *means* must not depend
on EBI being up — and because the outage case has to be testable, being the
one that matters most.
"""

from __future__ import annotations

import pytest

from metaseed.services.term_check import (
    Outcome,
    check_entity_terms,
    check_term,
    ontology_of,
)


class _Source:
    """A stand-in ontology: it knows the ids it was given, and nothing else."""

    def __init__(self, known: set[str] | None = None, fails: bool = False) -> None:
        self.known = known or set()
        self.fails = fails

    def get_term_sync(self, term_id: str) -> object | None:
        if self.fails:
            raise ConnectionError("OLS is down")
        return object() if term_id in self.known else None


class TestReadingATermId:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("TO:0000387", "to"),
            ("NCBITaxon_3702", "ncbitaxon"),
            ("PATO:0000001", "pato"),
            ("just a label", None),
        ],
    )
    def test_the_ontology_a_term_names(self, value: str, expected: str | None) -> None:
        assert ontology_of(value) == expected


class TestCheckingAValue:
    def test_a_term_from_the_named_ontology_is_fine(self) -> None:
        verdict = check_term("TO:0000387", ["to", "co_321"], _Source({"TO:0000387"}))

        assert verdict.outcome is Outcome.OK
        assert not verdict.is_problem

    def test_a_term_from_another_ontology_is_refused_without_asking(self) -> None:
        """The pointer is the point: a phenotype term does not belong in a
        field that takes a trait term, whatever OLS says about it."""
        verdict = check_term("PATO:0000001", ["to"], _Source({"PATO:0000001"}))

        assert verdict.outcome is Outcome.NOT_IN_ONTOLOGY
        assert verdict.is_problem
        assert "pato" in verdict.message and "to" in verdict.message

    def test_a_term_the_ontology_does_not_have_is_reported(self) -> None:
        verdict = check_term("TO:9999999", ["to"], _Source(set()))

        assert verdict.outcome is Outcome.NOT_FOUND
        assert verdict.is_problem


class TestWhenTheServiceIsDown:
    """Someone else's outage must not mark a researcher's data invalid."""

    def test_an_outage_is_not_checked_rather_than_invalid(self) -> None:
        verdict = check_term("TO:0000387", ["to"], _Source(fails=True))

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem
        assert "did not answer" in verdict.message

    def test_a_label_is_not_checked_rather_than_wrong(self) -> None:
        """Most values people type are labels, not identifiers."""
        verdict = check_term("leaf", ["to"], _Source())

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem


class TestCheckingAnEntity:
    def test_only_ontology_fields_with_a_value_are_checked(self) -> None:
        from metaseed.specs.schema import FieldSpec, FieldType

        fields = [
            FieldSpec(name="title", type=FieldType.STRING),
            FieldSpec(name="trait", type=FieldType.ONTOLOGY_TERM, ontologies=["to"]),
            FieldSpec(name="unit", type=FieldType.ONTOLOGY_TERM, ontologies=["uo"]),
        ]
        data = {"title": "anything", "trait": "TO:0000387", "unit": ""}

        verdicts = check_entity_terms(fields, data, _Source({"TO:0000387"}))

        assert set(verdicts) == {"trait"}
        assert verdicts["trait"].outcome is Outcome.OK
