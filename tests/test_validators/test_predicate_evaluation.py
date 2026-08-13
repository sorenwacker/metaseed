"""Evaluating a rule predicate against one record (#211, ADR 003).

The semantics are chosen so a rule cannot silently stop firing: an absent field
is false for every operator but `is_not_set`, a type mismatch on an equality
operator is false, and an ordering operator applied to operands that cannot be
ordered raises against that record rather than returning a quiet false — which
would disable the constraint for exactly the records it was written to catch.

The model itself, its bounds and its rendering live in `metaseed.specs`: a
predicate is part of the spec format, and evaluating one is what this layer
does with it.
"""

from __future__ import annotations

from datetime import date

import pytest

from metaseed.specs.predicates import parse_predicate
from metaseed.validators.predicates import PredicateError, evaluate


class TestEvaluation:
    @pytest.mark.parametrize(
        ("op", "value", "expected"),
        [
            ("==", "CV", True),
            ("==", "other", False),
            ("!=", "other", True),
            ("!=", "CV", False),
            ("in", ["CV", "String"], True),
            ("in", ["String"], False),
            ("not_in", ["String"], True),
            ("is_set", None, True),
            ("is_not_set", None, False),
        ],
    )
    def test_the_operators(self, op: str, value: object, expected: bool) -> None:
        predicate = parse_predicate({"field": "data_type", "op": op, "value": value})

        assert evaluate(predicate, {"data_type": "CV"}) is expected

    @pytest.mark.parametrize(
        "op", ["==", "!=", "in", "not_in", ">", ">=", "<", "<=", "is_set"]
    )
    def test_an_absent_field_is_false_for_everything_but_is_not_set(
        self, op: str
    ) -> None:
        predicate = parse_predicate({"field": "missing", "op": op, "value": [1]})

        assert evaluate(predicate, {"other": 1}) is False

    def test_an_absent_field_is_true_for_is_not_set(self) -> None:
        predicate = parse_predicate({"field": "missing", "op": "is_not_set"})

        assert evaluate(predicate, {"other": 1}) is True

    def test_a_null_reads_as_absent(self) -> None:
        predicate = parse_predicate({"field": "name", "op": "is_not_set"})

        assert evaluate(predicate, {"name": None}) is True

    def test_an_empty_string_reads_as_absent(self) -> None:
        """`has_value` is what the rest of the validator means by "set", and a
        predicate must not mean something else."""
        predicate = parse_predicate({"field": "name", "op": "is_not_set"})

        assert evaluate(predicate, {"name": ""}) is True
        assert evaluate(predicate, {"tags": []}) is True

    def test_a_type_mismatch_is_false_not_an_error(self) -> None:
        predicate = parse_predicate({"field": "count", "op": "==", "value": "3"})

        assert evaluate(predicate, {"count": 3}) is False

    def test_a_boolean_is_not_the_integer_one(self) -> None:
        """Python says `True == 1`; a spec that asks for `true` does not."""
        predicate = parse_predicate(
            {"field": "is_display_column", "op": "==", "value": True}
        )

        assert evaluate(predicate, {"is_display_column": 1}) is False
        assert evaluate(predicate, {"is_display_column": True}) is True

    @pytest.mark.parametrize(
        ("op", "expected"), [(">", True), (">=", True), ("<", False), ("<=", False)]
    )
    def test_numbers_order(self, op: str, expected: bool) -> None:
        predicate = parse_predicate({"field": "n", "op": op, "value": 3})

        assert evaluate(predicate, {"n": 5}) is expected

    def test_dates_order(self) -> None:
        predicate = parse_predicate(
            {"field": "start", "op": ">=", "value": "2026-01-01"}
        )

        assert evaluate(predicate, {"start": date(2026, 6, 1)}) is True
        assert evaluate(predicate, {"start": "2025-06-01"}) is False

    def test_an_unorderable_comparison_is_an_error_against_the_record(self) -> None:
        """Not a false: a mistyped comparison must not quietly disable the
        constraint for exactly the records it was written to catch."""
        predicate = parse_predicate({"field": "name", "op": ">", "value": 3})

        with pytest.raises(PredicateError) as caught:
            evaluate(predicate, {"name": "Input"})

        assert "name" in str(caught.value)

    def test_all_requires_every_member(self) -> None:
        predicate = parse_predicate(
            {
                "all": [
                    {"field": "isa_tag", "op": "in", "value": ["source", "protocol"]},
                    {"field": "name", "op": "!=", "value": "Input"},
                ]
            }
        )

        assert evaluate(predicate, {"isa_tag": "source", "name": "Origin"}) is True
        assert evaluate(predicate, {"isa_tag": "source", "name": "Input"}) is False

    def test_any_requires_one(self) -> None:
        predicate = parse_predicate(
            {
                "any": [
                    {"field": "name", "op": "is_not_set"},
                    {"field": "name", "op": "!=", "value": "Input"},
                ]
            }
        )

        assert evaluate(predicate, {}) is True

    def test_not_inverts(self) -> None:
        predicate = parse_predicate({"not": {"field": "name", "op": "is_set"}})

        assert evaluate(predicate, {"name": "x"}) is False
        assert evaluate(predicate, {}) is True
