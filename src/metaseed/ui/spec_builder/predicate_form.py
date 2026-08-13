"""Editing a rule predicate as rows, rather than as text.

A predicate is stored as a structured mapping (:mod:`metaseed.specs.predicates`),
and this is how a person builds one: repeated (field, operator, value) rows with
an all/any toggle. The field is chosen from the fields the counted entity
actually declares, which is what makes the load-time "unknown field" error
unreachable from the editor — a free-text box would move that whole class of
mistake to load time, after saving.

A flat group of comparisons is what the rows can express. A predicate loaded
from YAML that nests deeper is rendered read-only with its one-line spelling and
left alone; it is neither flattened nor dropped.

Values are read as YAML, which is how the same value would be written in the
profile: ``true`` is a boolean, ``3`` a number, ``[a, b]`` a list, anything else
text. Without that, every value would arrive as a string and a predicate over a
boolean column could never match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from metaseed.specs.predicates import AllOf, AnyOf, Comparison, parse_predicate

if TYPE_CHECKING:
    from metaseed.specs.predicates import NotPredicate, Predicate
    from metaseed.specs.schema import ProfileSpec

SET_OPERATORS = ("is_set", "is_not_set")
OPERATORS = ("==", "!=", "in", "not_in", ">", ">=", "<", "<=", *SET_OPERATORS)


def rows_from_predicate(
    where: Comparison | AllOf | AnyOf | NotPredicate | None,
) -> tuple[str, list[dict[str, Any]]] | None:
    """The predicate as editable rows, or ``None`` when it does not fit the form.

    Args:
        where: The rule's predicate, if it has one.

    Returns:
        ``(join, rows)`` where join is ``"all"`` or ``"any"``, or ``None`` for a
        predicate the row builder cannot represent.
    """
    if where is None:
        return "all", []
    if isinstance(where, Comparison):
        return "all", [_row(where)]
    if isinstance(where, AllOf | AnyOf):
        members = where.all if isinstance(where, AllOf) else where.any
        if all(isinstance(member, Comparison) for member in members):
            join = "all" if isinstance(where, AllOf) else "any"
            return join, [_row(m) for m in members]  # type: ignore[arg-type]
    return None


def predicate_from_rows(
    join: str,
    fields: list[str],
    operators: list[str],
    values: list[str],
) -> Predicate | None:
    """Assemble the posted rows into a predicate.

    A row with no field is an empty row the person left behind, not an error.

    Args:
        join: ``"all"`` or ``"any"``.
        fields: The field of each row.
        operators: The operator of each row.
        values: The value of each row, as typed.

    Returns:
        The predicate, or ``None`` when no row carries a field.

    Raises:
        ValueError: If a row names an operator that does not exist, or a value
            that is not readable.
    """
    comparisons: list[dict[str, Any]] = []
    for index, field in enumerate(fields):
        name = field.strip()
        if not name:
            continue
        operator = operators[index].strip() if index < len(operators) else "=="
        if operator not in OPERATORS:
            raise ValueError(f"Unknown operator '{operator}'")
        comparison: dict[str, Any] = {"field": name, "op": operator}
        if operator not in SET_OPERATORS:
            text = values[index] if index < len(values) else ""
            if not text.strip():
                raise ValueError(f"Operator '{operator}' on '{name}' needs a value")
            comparison["value"] = _as_value(text)
        comparisons.append(comparison)

    if not comparisons:
        return None
    if len(comparisons) == 1:
        return parse_predicate(comparisons[0])
    key = "any" if join == "any" else "all"
    return parse_predicate({key: comparisons})


def list_field_options(spec: ProfileSpec) -> list[dict[str, Any]]:
    """Every list-of-entity field in the profile, with the fields of its items.

    Feeds both selectors in the form: which list a cardinality rule counts, and
    which of the counted entity's fields a predicate row may name.
    """
    options: list[dict[str, Any]] = []
    for entity_name, entity in spec.entities.items():
        for field in entity.fields:
            item = spec.entities.get(field.items) if field.items else None
            if item is None:
                continue
            options.append(
                {
                    "entity": entity_name,
                    "field": field.name,
                    "items": field.items,
                    "item_fields": [f.name for f in item.fields],
                }
            )
    return options


def _row(comparison: Comparison) -> dict[str, Any]:
    """One comparison as a form row."""
    return {
        "field": comparison.field,
        "op": comparison.op,
        "value": "" if comparison.value is None else _as_text(comparison.value),
    }


def _as_value(text: str) -> Any:
    """A typed value from what the person typed, read the way YAML would read it."""
    stripped = text.strip()
    try:
        return yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not read the value {text!r}: {exc}") from exc


def _as_text(value: Any) -> str:
    """A stored value back as the text that produced it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        # Flow style, so what is shown reads back as the same list rather than
        # as one string with commas in it.
        return str(yaml.safe_dump(value, default_flow_style=True).strip())
    return str(value)
