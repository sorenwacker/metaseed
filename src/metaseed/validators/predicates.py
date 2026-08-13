"""Evaluating a rule predicate against one record.

The model, its bounds and its rendering are :mod:`metaseed.specs.predicates` —
a predicate is part of the spec format. This is what the validator does with
one: read the named field off the record in front of it, and answer whether the
record is in the subset the rule applies to.

There is no parser and no ``eval``. The structure is walked with a fixed
operator table, which is why the safety bound can be structural and checked once
at load rather than timed per value.

Every semantic choice here answers the same question: what happens when a
predicate cannot be applied? A silent ``False`` would exclude the record from
the rule — that is, disable the constraint for exactly the records it was
written to catch, which is the failure #211 reports. So an operand mismatch that
could be a typo raises (:class:`PredicateError`), while the cases an author can
reasonably mean — an absent field, a type that simply differs — are false and
documented as such.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from metaseed.specs.predicates import AllOf, AnyOf, Comparison, NotPredicate
from metaseed.validators.base import has_value

if TYPE_CHECKING:
    from collections.abc import Callable

Predicate = Comparison | AllOf | AnyOf | NotPredicate


class PredicateError(Exception):
    """A predicate could not be applied to a record.

    Raised rather than answered ``False`` so a mistyped comparison surfaces as
    an error against the record instead of quietly excluding it from the rule.
    """


def evaluate(predicate: Predicate, record: dict[str, Any]) -> bool:
    """Whether ``record`` is in the subset ``predicate`` selects.

    Args:
        predicate: The predicate to apply.
        record: The record it sees — for a ``cardinality`` ``where``, one item
            of the list the rule names, not the parent that declares it.

    Returns:
        True when the record matches.

    Raises:
        PredicateError: If an ordering operator was given operands that cannot
            be ordered.
    """
    if isinstance(predicate, AllOf):
        return all(evaluate(member, record) for member in predicate.all)
    if isinstance(predicate, AnyOf):
        return any(evaluate(member, record) for member in predicate.any)
    if isinstance(predicate, NotPredicate):
        return not evaluate(predicate.not_, record)
    return _compare(predicate, record)


def _compare(comparison: Comparison, record: dict[str, Any]) -> bool:
    """Apply one leaf test."""
    present = has_value(record, comparison.field)
    if comparison.op == "is_set":
        return present
    if comparison.op == "is_not_set":
        return not present
    if not present:
        # Every other operator is false for an absent field. A predicate over an
        # optional field therefore selects only the records where it is set; the
        # other reading is written as `any: [is_not_set, ...]`.
        return False

    value = record[comparison.field]
    expected = comparison.value

    if comparison.op == "==":
        return _equal(value, expected)
    if comparison.op == "!=":
        return not _equal(value, expected)
    if comparison.op in {"in", "not_in"}:
        member = isinstance(expected, list) and any(
            _equal(value, item) for item in expected
        )
        return member if comparison.op == "in" else not member
    return _ordered(comparison, value, expected)


def _equal(value: Any, expected: Any) -> bool:
    """Equality that does not conflate types.

    Python holds that ``True == 1``; a spec asking for ``true`` does not mean
    ``1``, and a spec asking for ``"3"`` does not mean ``3``. A mismatch is
    simply false — the author wrote a value of one type and the data holds
    another, which is a legitimate thing for a predicate to select against.
    """
    if isinstance(value, bool) != isinstance(expected, bool):
        return False
    if isinstance(value, str) != isinstance(expected, str):
        return False
    return bool(value == expected)


_ORDERINGS: dict[str, Callable[[Any, Any], bool]] = {
    ">": lambda a, b: bool(a > b),
    ">=": lambda a, b: bool(a >= b),
    "<": lambda a, b: bool(a < b),
    "<=": lambda a, b: bool(a <= b),
}


def _ordered(comparison: Comparison, value: Any, expected: Any) -> bool:
    """Apply an ordering operator, or say why it cannot be applied."""
    pair = _as_numbers(value, expected) or _as_dates(value, expected)
    if pair is None:
        raise PredicateError(
            f"cannot compare '{comparison.field}' with {comparison.op}: "
            f"{value!r} and {expected!r} are not both numbers or both dates"
        )
    left, right = pair
    return _ORDERINGS[comparison.op](left, right)


def _as_numbers(value: Any, expected: Any) -> tuple[Any, Any] | None:
    """Both operands as numbers, or ``None`` when they are not both numeric."""
    if isinstance(value, bool) or isinstance(expected, bool):
        return None
    if isinstance(value, int | float) and isinstance(expected, int | float):
        return value, expected
    return None


def _as_dates(value: Any, expected: Any) -> tuple[date, date] | None:
    """Both operands as dates, or ``None`` when either is not one.

    An ISO string counts: a profile YAML has no date literal inside a predicate
    value, so ``value: "2026-01-01"`` is how an author writes one.
    """
    left, right = _as_date(value), _as_date(expected)
    if left is None or right is None:
        return None
    return left, right


def _as_date(value: Any) -> date | None:
    """One operand as a date, or ``None``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
