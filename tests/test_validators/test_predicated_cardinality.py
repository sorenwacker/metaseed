"""A cardinality rule counts the items a predicate selects (#211, ADR 003).

Without `where` a cardinality rule counts the whole list, so "exactly one
attribute is the display column" was inexpressible and lived in a checker
outside metaseed — which found a template with zero display columns that
metaseed reported as valid. That template is the first case here.

The message shape is the other half of the fix: "expected exactly 1, got 0" is
unactionable against 24 children, so a predicated failure states the bound, the
matched count, the population, the predicate as a sentence, and — where the
count is too high — which members were counted.
"""

from __future__ import annotations

import pytest

from metaseed.specs.predicates import parse_predicate
from metaseed.validators.base import Kind
from metaseed.validators.rules import ListCardinalityRule


def _rule(**kwargs: object) -> ListCardinalityRule:
    """A rule over `attributes`, selecting the display column."""
    defaults: dict = {
        "field": "attributes",
        "where": parse_predicate(
            {"field": "is_display_column", "op": "==", "value": True}
        ),
        "rule_name": "exactly_one_display_column",
        "label_field": "name",
    }
    return ListCardinalityRule(**{**defaults, **kwargs})  # type: ignore[arg-type]


def _attributes(*display_flags: bool) -> dict:
    return {
        "attributes": [
            {"name": f"Attribute {i}", "is_display_column": flag}
            for i, flag in enumerate(display_flags)
        ]
    }


class TestCountingTheSubset:
    def test_the_template_that_slipped_through(self) -> None:
        """Zero display columns among 24 attributes: valid today, reported now."""
        errors = _rule(min_items=1, max_items=1).validate(_attributes(*[False] * 24))

        assert len(errors) == 1
        assert (
            "expected exactly 1 of 24 'attributes' to match "
            "is_display_column == true, found 0" in errors[0].message
        )

    def test_exactly_one_passes(self) -> None:
        assert _rule(min_items=1, max_items=1).validate(_attributes(False, True)) == []

    def test_two_are_named(self) -> None:
        errors = _rule(min_items=1, max_items=1).validate(
            _attributes(False, True, False, True)
        )

        assert len(errors) == 1
        assert "found 2: attributes[1] 'Attribute 1', attributes[3] 'Attribute 3'" in (
            errors[0].message
        )

    def test_a_lower_bound_alone_says_at_least(self) -> None:
        errors = _rule(min_items=1).validate(_attributes(False, False))

        assert "expected at least 1 of 2" in errors[0].message

    def test_an_upper_bound_alone_says_at_most(self) -> None:
        errors = _rule(max_items=1).validate(_attributes(True, True))

        assert "expected at most 1 of 2" in errors[0].message

    def test_the_whole_list_is_counted_without_a_predicate(self) -> None:
        rule = ListCardinalityRule(field="attributes", max_items=1)

        errors = rule.validate(_attributes(False, False))

        assert len(errors) == 1
        assert "must have at most 1 item(s), but has 2" in errors[0].message

    def test_a_missing_list_counts_as_empty(self) -> None:
        errors = _rule(min_items=1).validate({})

        assert "found 0" in errors[0].message

    def test_an_item_that_is_not_a_record_matches_nothing(self) -> None:
        """A predicate reads fields; a bare string has none. Rejected at load,
        but a dataset can still hold one, and it must not crash the run."""
        errors = _rule(min_items=1).validate({"attributes": ["Attribute 0"]})

        assert "found 0" in errors[0].message

    def test_a_label_falls_back_to_the_index(self) -> None:
        rule = _rule(min_items=1, max_items=1, label_field=None)

        errors = rule.validate(_attributes(True, True))

        assert "found 2: attributes[0], attributes[1]" in errors[0].message


class TestHowItReports:
    def test_a_shortfall_is_incompleteness_not_a_wrong_value(self) -> None:
        """Same as an unpredicated lower bound: something is missing, which must
        not block saving what is already there."""
        errors = _rule(min_items=1).validate(_attributes(False))

        assert errors[0].kind is Kind.COMPLETENESS

    def test_an_excess_is_a_wrong_value(self) -> None:
        errors = _rule(max_items=1).validate(_attributes(True, True))

        assert errors[0].kind is Kind.VALUE

    def test_a_custom_message_keeps_the_counts(self) -> None:
        """For an unpredicated rule a custom message replaces the generated one.
        For a predicated rule that would throw away the only actionable part, so
        it is prefixed instead."""
        rule = _rule(
            min_items=1, max_items=1, message="Every sample type needs a title"
        )

        errors = rule.validate(_attributes(False))

        assert errors[0].message.startswith("Every sample type needs a title")
        assert "found 0" in errors[0].message

    def test_an_unapplicable_predicate_is_reported_against_the_record(self) -> None:
        """A silent false would exclude the record from the rule — disabling the
        constraint for exactly the data it was written to catch."""
        rule = ListCardinalityRule(
            field="attributes",
            min_items=1,
            where=parse_predicate({"field": "name", "op": ">", "value": 3}),
            rule_name="broken",
        )

        errors = rule.validate({"attributes": [{"name": "Input"}]})

        assert len(errors) == 1
        assert "cannot compare 'name'" in errors[0].message
        assert errors[0].kind is Kind.VALUE


class TestTheRuleName:
    def test_it_carries_the_declared_name(self) -> None:
        errors = _rule(min_items=1).validate(_attributes(False))

        assert errors[0].rule == "exactly_one_display_column"

    @pytest.mark.parametrize("bound", ["min_items", "max_items"])
    def test_the_field_is_the_list(self, bound: str) -> None:
        errors = _rule(**{bound: 0 if bound == "max_items" else 5}).validate(
            _attributes(True)
        )

        assert errors[0].field == "attributes"
