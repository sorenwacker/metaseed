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


class TestAnOntologyTheSourceDoesNotCarry:
    """OLS4 hosts `to` but not `co_321`, and MIAPPE names them together. A
    valid Crop Ontology term must not be called missing because the lookup
    cannot see that vocabulary."""

    class _PartialSource:
        def __init__(self, carries: set[str]) -> None:
            self.carries = carries

        def get_term_sync(self, term_id: str) -> object | None:
            return None

        def has_ontology_sync(self, ontology_id: str) -> bool | None:
            return ontology_id in self.carries

    def test_a_term_from_an_unavailable_ontology_is_not_checked(self) -> None:
        verdict = check_term(
            "CO_321:0000123", ["to", "co_321"], self._PartialSource({"to"})
        )

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem
        assert "does not carry" in verdict.message

    def test_a_missing_term_from_a_carried_ontology_is_still_reported(self) -> None:
        verdict = check_term("TO:9999999", ["to"], self._PartialSource({"to"}))

        assert verdict.outcome is Outcome.NOT_FOUND
        assert verdict.is_problem


class TestNoListMeansAnyOntology:
    """A field that names no ontology takes a term from any of them.

    Not "no lookup at all", which is how a consumer keying its picker off this
    key read it: `isa` and `seek` both declare
    `OntologyAnnotation.term_accession` as `ontology_term` with no `ontologies`
    list, so the one field whose declared *type* is literally "ontology term"
    offered nothing (#246). The behaviour was already right; nothing pinned it,
    so nothing stopped it being "tidied" into a restriction.
    """

    class _Source:
        def get_term_sync(self, term_id: str) -> object | None:
            return object() if term_id == "PATO:0000001" else None

        def has_ontology_sync(self, ontology_id: str) -> bool | None:
            return True

    def test_a_real_term_passes_whatever_ontology_it_is_from(self) -> None:
        assert check_term("PATO:0000001", None, self._Source()).outcome is Outcome.OK

    def test_an_empty_list_reads_the_same_as_none(self) -> None:
        assert check_term("PATO:0000001", [], self._Source()).outcome is Outcome.OK

    def test_a_term_that_does_not_exist_is_still_reported(self) -> None:
        """Unrestricted is not unchecked."""
        verdict = check_term("PATO:9999999", None, self._Source())

        assert verdict.outcome is Outcome.NOT_FOUND
        assert verdict.is_problem

    def test_no_field_is_ever_told_its_ontology_is_wrong(self) -> None:
        """NOT_IN_ONTOLOGY cannot arise without a declared list."""
        for value in ("PATO:0000001", "CO_321:0000123", "TO:0000387"):
            assert (
                check_term(value, None, self._Source()).outcome
                is not Outcome.NOT_IN_ONTOLOGY
            )


def test_the_profiles_that_rely_on_this_still_do() -> None:
    """If isa or seek gains an ontologies list, this test should be revisited
    rather than silently kept passing by the general rule above."""
    from metaseed.specs.loader import SpecLoader

    unrestricted = []
    for profile, version in (("isa", "1.0"), ("seek", "1.0")):
        spec = SpecLoader(profile=profile).load_profile(version, profile)
        for entity in spec.entities.values():
            for field in entity.fields:
                if field.type == "ontology_term" and not field.ontologies:
                    unrestricted.append(f"{profile}: {field.name}")

    assert unrestricted, (
        "no shipped profile declares an unrestricted ontology_term any more; "
        "the documented meaning of an absent list now rests on nothing"
    )
