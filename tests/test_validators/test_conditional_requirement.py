"""A requirement that depends on another field's *value* (#211, ADR 003).

The legacy `condition` splits on whitespace and asks whether each remaining
token is a field that has a value. It never reads a value, so "cv_terms is
required when data_type is Controlled Vocabulary" could not be written — the
first of the four SEEK constraints that had to live outside metaseed.

`when` is a predicate and `require` is the list of fields it demands. They are
an alternative to `condition`, not a layer over it: a rule setting both is
rejected at load rather than resolved by a precedence nobody would remember.
"""

from __future__ import annotations

from metaseed.specs.predicates import parse_predicate
from metaseed.validators.base import Kind
from metaseed.validators.rules import ConditionalRequirementRule


def _rule(*fields: str, **kwargs: object) -> ConditionalRequirementRule:
    return ConditionalRequirementRule(
        when=parse_predicate(
            {"field": "data_type", "op": "==", "value": "Controlled Vocabulary"}
        ),
        require=list(fields) or ["cv_terms"],
        rule_name="cv_terms_required_for_controlled_vocabulary",
        **kwargs,  # type: ignore[arg-type]
    )


class TestWhenItApplies:
    def test_the_required_field_is_demanded(self) -> None:
        errors = _rule().validate({"data_type": "Controlled Vocabulary"})

        assert len(errors) == 1
        assert errors[0].field == "cv_terms"
        assert "required when data_type == 'Controlled Vocabulary'" in errors[0].message

    def test_a_present_value_satisfies_it(self) -> None:
        assert (
            _rule().validate(
                {"data_type": "Controlled Vocabulary", "cv_terms": ["a", "b"]}
            )
            == []
        )

    def test_an_empty_value_does_not(self) -> None:
        """`has_value` is what the rest of the validator means by present, and a
        rule that accepted an empty list would be satisfied by nothing."""
        errors = _rule().validate(
            {"data_type": "Controlled Vocabulary", "cv_terms": []}
        )

        assert len(errors) == 1

    def test_each_missing_field_is_reported_on_its_own(self) -> None:
        errors = _rule("cv_terms", "cv_source").validate(
            {"data_type": "Controlled Vocabulary"}
        )

        assert [e.field for e in errors] == ["cv_terms", "cv_source"]


class TestWhenItDoesNot:
    def test_another_value_demands_nothing(self) -> None:
        assert _rule().validate({"data_type": "String"}) == []

    def test_an_absent_field_demands_nothing(self) -> None:
        """A predicate over an absent field selects nothing, so a record that
        has not said what it is yet is not told it is missing something."""
        assert _rule().validate({}) == []


class TestHowItReports:
    def test_a_demand_is_incompleteness_not_a_wrong_value(self) -> None:
        errors = _rule().validate({"data_type": "Controlled Vocabulary"})

        assert errors[0].kind is Kind.COMPLETENESS
        assert not errors[0].blocks

    def test_a_custom_message_keeps_the_reason(self) -> None:
        errors = _rule(message="A controlled vocabulary needs its terms").validate(
            {"data_type": "Controlled Vocabulary"}
        )

        assert errors[0].message.startswith("A controlled vocabulary needs its terms")
        assert "data_type == 'Controlled Vocabulary'" in errors[0].message

    def test_an_unapplicable_predicate_is_reported_against_the_record(self) -> None:
        rule = ConditionalRequirementRule(
            when=parse_predicate({"field": "name", "op": ">", "value": 3}),
            require=["cv_terms"],
            rule_name="broken",
        )

        errors = rule.validate({"name": "Input"})

        assert len(errors) == 1
        assert "cannot compare 'name'" in errors[0].message
        assert errors[0].kind is Kind.VALUE
