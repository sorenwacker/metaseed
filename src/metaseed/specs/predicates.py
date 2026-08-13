"""The predicate a validation rule may carry, and what may be written in one.

A rule about *some* of a collection could not be written: ``cardinality``
counted every item of a list, so "exactly one attribute is the display column"
had to live in a checker outside metaseed — which promptly found a template that
metaseed reported as valid (#211). ``where`` names the subset a rule counts.

A predicate is a **structured mapping**, not an expression string. Its leaf form
is ``{field, op, value}``; its composite forms are ``{all: [...]}``,
``{any: [...]}`` and ``{not: {...}}``. The deciding reason is the content hash:
:func:`~metaseed.specs.versioning.canonical_json` sorts keys, so a mapping is
canonical for free, while ``a=='X'`` and ``a == 'X'`` would be two documents with
two hashes — and because the comparator reports any rule inequality as breaking,
reformatting a predicate would force a MAJOR bump. The one-line spelling survives
as the *rendering* (:func:`render_predicate`), which is what error messages and
the rule editor show.

This module holds the format: the model, what is legal in one, and how to read
it back as a sentence. Evaluating a predicate against a record is
:mod:`metaseed.validators.predicates` — a predicate is part of the spec, and
enforcing it is what the layer above does with it.

See ADR 003 for the alternatives weighed, and ``docs/api/schema-specs.md`` for
the authoring reference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

if TYPE_CHECKING:
    from metaseed.specs.schema import EntityDefSpec, ProfileSpec, ValidationRuleSpec

Operator = Literal[
    "==", "!=", "in", "not_in", ">", ">=", "<", "<=", "is_set", "is_not_set"
]
"""The operators a predicate may use.

``matches`` is deliberately absent: a user-supplied regex is hostile input this
repository already has to bound in time (``rules._matches_within_timeout``), and
leaving it out is what lets the bounds below be structural and checked once.
"""

MEMBERSHIP_OPERATORS: frozenset[str] = frozenset({"in", "not_in"})
ORDERING_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<="})
SET_OPERATORS: frozenset[str] = frozenset({"is_set", "is_not_set"})

MAX_DEPTH = 8
"""Deepest nesting accepted. Bounds the recursion; no real constraint approaches it."""

MAX_NODES = 64
"""Most nodes accepted in one predicate. Bounds the walk."""

MAX_LITERAL_ITEMS = 256
"""Longest literal list accepted. Bounds the cost of ``in``/``not_in``."""


class Comparison(BaseModel):
    """One test against one field of the record being examined.

    Attributes:
        field: The field to read, on the record the rule's predicate sees.
        op: How to compare it.
        value: What to compare it against. Omitted for ``is_set``/``is_not_set``.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    op: Operator
    value: Any = None


class AllOf(BaseModel):
    """Every member must hold."""

    model_config = ConfigDict(extra="forbid")

    all: list[Predicate]


class AnyOf(BaseModel):
    """At least one member must hold."""

    model_config = ConfigDict(extra="forbid")

    any: list[Predicate]


class NotPredicate(BaseModel):
    """The member must not hold.

    The YAML key is ``not``, which cannot be an attribute name, so it is carried
    as an alias — serialized by alias too, or a spec written back to disk would
    say ``not_`` and fail to load again.
    """

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    not_: Predicate = Field(alias="not")


Predicate = Annotated[
    Union[Comparison, AllOf, AnyOf, NotPredicate],  # noqa: UP007 - Pydantic union
    Field(union_mode="left_to_right"),
]
"""A leaf test, or a group of them."""

AllOf.model_rebuild()
AnyOf.model_rebuild()
NotPredicate.model_rebuild()


_PREDICATE_ADAPTER: TypeAdapter[Comparison | AllOf | AnyOf | NotPredicate] = (
    TypeAdapter(Predicate)
)


def parse_predicate(
    mapping: dict[str, Any],
) -> Comparison | AllOf | AnyOf | NotPredicate:
    """Build a predicate from its mapping form.

    Args:
        mapping: The ``where`` value as written in YAML or posted by a tool.

    Returns:
        The parsed predicate.

    Raises:
        pydantic.ValidationError: If it is not one of the four shapes, or names
            an operator that does not exist.
    """
    return _PREDICATE_ADAPTER.validate_python(mapping)


def render_predicate(predicate: Comparison | AllOf | AnyOf | NotPredicate) -> str:
    """Render a predicate as the one-line sentence it states.

    This is the reader-facing spelling — error messages, the rules list, the
    editor's read-only view of a predicate too nested to edit as rows. It is not
    a storage format and is never parsed back.

    Args:
        predicate: The predicate to render.

    Returns:
        e.g. ``isa_tag in ['source', 'protocol'] and name != 'Input'``.
    """
    if isinstance(predicate, Comparison):
        if predicate.op == "is_set":
            return f"{predicate.field} is set"
        if predicate.op == "is_not_set":
            return f"{predicate.field} is not set"
        return f"{predicate.field} {predicate.op} {_literal(predicate.value)}"
    if isinstance(predicate, NotPredicate):
        return f"not ({render_predicate(predicate.not_)})"
    members, joiner = (
        (predicate.all, " and ")
        if isinstance(predicate, AllOf)
        else (predicate.any, " or ")
    )
    return joiner.join(_grouped(member) for member in members)


def predicate_issues(
    predicate: Comparison | AllOf | AnyOf | NotPredicate,
    known_fields: set[str] | None,
) -> list[str]:
    """Everything wrong with a predicate, checked once at load rather than per record.

    A predicate naming a field the entity does not declare is a rule that never
    fires — the defect class #211 reports — so it is rejected loudly at profile
    load and listed by ``spec_validate`` while a draft is being edited. The
    bounds are structural rather than temporal because the form has no
    backtracking: worst case is ``MAX_NODES`` times ``MAX_LITERAL_ITEMS`` primitive
    comparisons per record, known before any record is seen.

    Args:
        predicate: The predicate to check.
        known_fields: The fields of the record it will be evaluated against, or
            ``None`` when the caller cannot resolve them — an unknown item
            entity is the caller's finding, and inventing field errors on top of
            it is noise.

    Returns:
        Human-readable problems, empty when there are none.
    """
    issues: list[str] = []
    nodes = 0

    def walk(node: Comparison | AllOf | AnyOf | NotPredicate, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > MAX_DEPTH:
            issues.append(
                f"predicate nests deeper than the maximum depth of {MAX_DEPTH}"
            )
            return
        if nodes > MAX_NODES:
            issues.append(f"predicate has more than the maximum of {MAX_NODES} nodes")
            return
        if isinstance(node, Comparison):
            issues.extend(_comparison_issues(node, known_fields))
            return
        if isinstance(node, NotPredicate):
            walk(node.not_, depth + 1)
            return
        members = node.all if isinstance(node, AllOf) else node.any
        key = "all" if isinstance(node, AllOf) else "any"
        if not members:
            issues.append(f"predicate group '{key}' is empty")
        for member in members:
            walk(member, depth + 1)

    walk(predicate, 1)
    # One report per kind: a predicate 40 levels deep would otherwise say so 40
    # times, and the first line is the actionable one.
    return list(dict.fromkeys(issues))


def _comparison_issues(node: Comparison, known_fields: set[str] | None) -> list[str]:
    """What is wrong with one leaf."""
    issues: list[str] = []
    if known_fields is not None and node.field not in known_fields:
        issues.append(
            f"predicate names field '{node.field}', which the entity does not "
            f"declare; the rule would never fire"
        )
    if node.op in SET_OPERATORS:
        if node.value is not None:
            issues.append(f"operator '{node.op}' takes no value")
    elif node.value is None:
        issues.append(f"operator '{node.op}' needs a value")
    elif node.op in MEMBERSHIP_OPERATORS:
        if not isinstance(node.value, list):
            issues.append(f"operator '{node.op}' needs a list value")
        elif len(node.value) > MAX_LITERAL_ITEMS:
            issues.append(
                f"literal list has {len(node.value)} entries, more than the "
                f"maximum of {MAX_LITERAL_ITEMS}"
            )
    return issues


def _grouped(predicate: Comparison | AllOf | AnyOf | NotPredicate) -> str:
    """Render a member, parenthesised when it is itself a group."""
    rendered = render_predicate(predicate)
    return f"({rendered})" if isinstance(predicate, AllOf | AnyOf) else rendered


def _literal(value: Any) -> str:
    """Render a literal the way the constraint reads, not the way Python repr does."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, list):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    if value is None:
        return "null"
    return str(value)


def profile_predicate_issues(profile: ProfileSpec) -> list[str]:
    """Everything wrong with the predicates a profile's rules carry.

    Checked at profile load, and again by ``spec_validate`` while a draft is
    edited, rather than when a record is validated: a predicate naming a field
    that does not exist is a rule that never fires, and a rule scoped to an
    entity nobody happens to validate would never be checked at all.

    Args:
        profile: The loaded profile.

    Returns:
        Human-readable problems, empty when there are none.
    """
    issues: list[str] = []
    for rule in profile.validation_rules:
        if rule.where is not None:
            issues.extend(_rule_issues(profile, rule))
        issues.extend(_requirement_issues(profile, rule))
    return issues


def _requirement_issues(profile: ProfileSpec, rule: ValidationRuleSpec) -> list[str]:
    """What is wrong with a rule's ``when``/``require`` pair.

    They are one construct in two keys, so half of it is an authoring mistake
    rather than a shorthand: a ``when`` with nothing to require never reports
    anything, and a ``require`` with no ``when`` is a plain required field
    written in the wrong place.
    """
    if rule.when is None and not rule.require:
        return []
    label = f"validation rule '{rule.name}'"
    if rule.when is None or not rule.require:
        return [f"{label}: 'when' and 'require' go together; one without the other"]
    if rule.condition:
        return [
            f"{label}: 'when' and 'condition' cannot both be set -- they are "
            f"alternatives, and a precedence between them would be a rule "
            f"nobody could remember"
        ]

    issues: list[str] = []
    for name, entity in _applicable_entities(profile, rule):
        declared = {f.name for f in entity.fields}
        issues.extend(
            f"{label}: {issue}" for issue in predicate_issues(rule.when, declared)
        )
        issues.extend(
            f"{label}: requires field '{field}', which {name} does not declare"
            for field in rule.require
            if field not in declared
        )
    return issues


def _applicable_entities(
    profile: ProfileSpec, rule: ValidationRuleSpec
) -> list[tuple[str, EntityDefSpec]]:
    """The entities a rule applies to, by name.

    ``applies_to: all`` is not resolved to every entity here: a requirement
    written for one entity and left unscoped would then report against all the
    others, which is noise rather than a finding.
    """
    if isinstance(rule.applies_to, str):
        names = [] if rule.applies_to == "all" else [rule.applies_to]
    else:
        names = list(rule.applies_to)
    return [
        (name, profile.entities[name]) for name in names if name in profile.entities
    ]


def _rule_issues(profile: ProfileSpec, rule: ValidationRuleSpec) -> list[str]:
    """What is wrong with one rule's predicate.

    Which record the predicate will see depends on the rule type, so which
    fields it may name does too: a ``cardinality`` predicate reads each *item*
    of the list the rule counts, a ``uniqueness`` predicate reads the record
    whose value is being counted.
    """
    label = f"validation rule '{rule.name}'"
    if not rule.field:
        return [f"{label}: 'where' needs a 'field'"]

    targets = _target_entities(profile, rule)
    if not targets:
        return [
            f"{label}: no entity it applies to declares a field '{rule.field}', "
            f"so the rule can never run"
        ]

    where = rule.where
    if where is None:  # pragma: no cover - the caller only passes rules with one
        return []
    if _is_uniqueness(rule):
        return [
            f"{label}: {issue}"
            for _name, entity in targets
            for issue in predicate_issues(where, {f.name for f in entity.fields})
        ]
    if not _is_cardinality(rule):
        return [
            f"{label}: 'where' is only supported on a cardinality or uniqueness rule"
        ]

    issues: list[str] = []
    for name, entity in targets:
        field = next((f for f in entity.fields if f.name == rule.field), None)
        item = profile.entities.get(field.items) if field and field.items else None
        if item is None:
            issues.append(
                f"{label}: '{name}.{rule.field}' is not a list of entities, so a "
                f"'where' has no fields to read"
            )
            continue
        issues.extend(
            f"{label}: {issue}"
            for issue in predicate_issues(where, {f.name for f in item.fields})
        )
    return issues


def _is_uniqueness(rule: ValidationRuleSpec) -> bool:
    """Whether a rule is a uniqueness rule, declared or inferred."""
    if rule.type:
        return rule.type == "uniqueness"
    return bool(rule.unique_within)


def _is_cardinality(rule: ValidationRuleSpec) -> bool:
    """Whether a rule is a cardinality rule, declared or inferred."""
    if rule.type:
        return rule.type == "cardinality"
    return rule.min_items is not None or rule.max_items is not None


def _target_entities(
    profile: ProfileSpec, rule: ValidationRuleSpec
) -> list[tuple[str, EntityDefSpec]]:
    """The entities a rule applies to that actually declare its field."""
    if isinstance(rule.applies_to, str):
        named = list(profile.entities)
    else:
        named = list(rule.applies_to)
    return [
        (name, profile.entities[name])
        for name in named
        if name in profile.entities
        and any(f.name == rule.field for f in profile.entities[name].fields)
    ]
