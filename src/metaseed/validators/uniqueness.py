"""Cross-record uniqueness, the one check a per-record engine cannot make.

An engine rule sees a single record and cannot see its siblings, so a declared
``uniqueness`` rule (MIAPPE's ``unique_within: parent`` on ``unique_id``, say)
is enforced here over the whole tree instead.

Separated from :mod:`metaseed.validators.dataset` because it is a self-contained
concern with its own vocabulary — rules, scope keys, and the accumulator that
lets a directory of files be checked as one dataset — and because that module
had grown past the project's 1000-line limit.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, NamedTuple, Self

from metaseed.specs.predicates import Predicate, render_predicate
from metaseed.specs.schema import ProfileSpec
from metaseed.utils import to_snake_case
from metaseed.validators.base import ValidationError
from metaseed.validators.predicates import PredicateError, evaluate

#: Walks an entity tree, calling ``visit(record, entity_type, path)`` for every
#: record. Supplied by the caller rather than reimplemented here.
TreeWalker = Callable[
    [dict[str, Any], str, Callable[[dict[str, Any], str, str], None], str], None
]


class UniquenessRule(NamedTuple):
    """A declared uniqueness rule, resolved for dataset-level enforcement."""

    name: str
    field: str
    scope: str  # "parent" or "global"
    applies_to: set[str]  # snake_case entity types, or {"all"}
    message: str | None
    where: Predicate | None = None  # which records are counted at all


def rules_from_profile(profile_spec: ProfileSpec | None) -> list[UniquenessRule]:
    """The uniqueness rules a profile declares, resolved for enforcement.

    Args:
        profile_spec: The loaded profile, or ``None`` when it could not be
            loaded — in which case there is nothing to enforce.

    Returns:
        One :class:`UniquenessRule` per declared rule.
    """
    if not profile_spec:
        return []

    rules: list[UniquenessRule] = []
    for rule in profile_spec.validation_rules:
        is_uniqueness = rule.type == "uniqueness" or (
            rule.type is None and bool(rule.unique_within)
        )
        if not is_uniqueness or not rule.field:
            continue
        applies = rule.applies_to
        if applies == "all" or isinstance(applies, str):
            applies_snake = {"all"} if applies == "all" else {to_snake_case(applies)}
        else:
            applies_snake = {to_snake_case(e) for e in applies}
        rules.append(
            UniquenessRule(
                name=rule.name,
                field=rule.field,
                scope=rule.unique_within or "parent",
                applies_to=applies_snake,
                message=rule.message,
                where=rule.where,
            )
        )
    return rules


class UniquenessChecker:
    """Applies a profile's uniqueness rules across records."""

    def __init__(self, rules: list[UniquenessRule]) -> None:
        """Hold the rules this checker enforces.

        Args:
            rules: Resolved rules, from :func:`rules_from_profile`.
        """
        self.rules = rules

    def check(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        seen: set[tuple[str, str, str]],
        traverse: TreeWalker,
        path: str = "",
        scope_prefix: str = "",
    ) -> list[ValidationError]:
        """Flag duplicate values for fields declared unique in the profile.

        Enforces the profile's uniqueness rules across records, which the
        per-record engine rule cannot. ``seen`` accumulates ``(rule, scope_key,
        value)`` keys so a caller may share it across files for global scope.

        Scope:
            - ``global``: unique across the whole dataset.
            - ``parent``: unique among siblings of the same collection. Two
              records share a parent scope when their paths differ only in the
              trailing list index, so the scope key is the path with that index
              stripped.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            seen: Accumulator of already-seen (rule, scope_key, value) keys.
            path: Current path for error reporting.
            scope_prefix: What distinguishes one parent from another beyond the
                path — the file, when a directory is validated with one shared
                accumulator. Without it two files' ``studies[0]`` are the same
                parent scope, and children of different parents collide.

        Returns:
            List of uniqueness validation errors.
        """
        if not self.rules:
            return []

        errors: list[ValidationError] = []

        def check_unique(d: dict[str, Any], etype: str, p: str) -> None:
            for rule in self.rules:
                if "all" not in rule.applies_to and etype not in rule.applies_to:
                    continue
                value = d.get(rule.field)
                if value is None:
                    continue
                if rule.where is not None and not self._selected(rule, d, p, errors):
                    # Outside the counted subset: not compared, and not recorded
                    # either, or an exempt record would still collide with the
                    # next one that is not exempt.
                    continue
                # Two records share a parent scope when their paths differ only
                # in the trailing list index, and — when a directory is
                # validated through one accumulator — when they are in the same
                # file. Computed outside the f-string: a backslash in an
                # f-string expression is a syntax error before Python 3.12.
                sibling_path = re.sub(r"\[\d+\]$", "", p)
                scope_key = (
                    "" if rule.scope == "global" else f"{scope_prefix}{sibling_path}"
                )
                key = (rule.name, scope_key, str(value))
                if key in seen:
                    field_path = f"{p}.{rule.field}" if p else rule.field
                    msg = rule.message or (
                        f"Value '{value}' is not unique for '{rule.field}' "
                        f"within {rule.scope} scope"
                    )
                    if rule.where is not None:
                        msg += (
                            f"; counted among records matching "
                            f"{render_predicate(rule.where)}"
                        )
                    errors.append(
                        ValidationError(
                            field=field_path, message=msg, rule="uniqueness"
                        )
                    )
                else:
                    seen.add(key)

        traverse(data, entity_type, check_unique, path)
        return errors

    def _selected(
        self: Self,
        rule: UniquenessRule,
        record: dict[str, Any],
        path: str,
        errors: list[ValidationError],
    ) -> bool:
        """Whether a record is in the subset a predicated uniqueness rule counts.

        A predicate that cannot be applied is reported against the record rather
        than read as "not selected": excluding it would leave the rule quietly
        satisfied by a predicate that never worked.
        """
        assert rule.where is not None
        try:
            return evaluate(rule.where, record)
        except PredicateError as exc:
            errors.append(
                ValidationError(
                    field=f"{path}.{rule.field}" if path else rule.field,
                    message=f"{rule.name}: {exc}",
                    rule="uniqueness",
                )
            )
            return False
