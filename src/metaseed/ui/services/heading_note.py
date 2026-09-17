"""The note on an exported column heading: what decides a valid value.

A person filling in a sheet has not read the specification. Whatever the
validation report would later hold against a value — its pattern, its length or
range, the values it may take, what it must refer to, the rules that name it —
belongs where the value is typed, not in a report after import.

A constraint can be declared on the field or in a profile-level rule. The note
shows it once, whichever declared it. See docs/architecture/excel-round-trip.md.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from typing import Any

from metaseed.specs.schema import PRIMITIVE_TYPES, FieldType

#: Allowed values listed in the note before it defers to the cell's dropdown.
MAX_LISTED_VALUES = 10

PARENT_NOTE = (
    "Structure, not metadata: which row of the parent sheet this row "
    "belongs to, named by that row's identifier.\n\n"
    "Written by the export — leave the existing values alone. If you "
    "add a row, choose its parent from the dropdown, or the row will "
    "have nothing to attach to on import."
)

_TYPE_WORDS: dict[Any, str] = {
    FieldType.STRING: "Text",
    FieldType.INTEGER: "Whole number",
    FieldType.FLOAT: "Decimal number",
    FieldType.BOOLEAN: "Yes/no",
    FieldType.DATE: "Date (YYYY-MM-DD)",
    FieldType.DATETIME: "Date and time",
    FieldType.URI: "Web address",
    FieldType.ONTOLOGY_TERM: "Ontology term",
}

_UNIQUE_WORDS = {"parent": "within the parent", "global": "across the dataset"}

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Characters per line a comment box of NOTE_WIDTH shows, for sizing its height.
_CHARS_PER_LINE = 48
NOTE_WIDTH = 360


def heading_note(column: str, field: Any, rules: Sequence[Any]) -> str:
    """What to tell someone hovering over a column heading.

    Args:
        column: The column name as written in the heading row.
        field: The column's :class:`FieldSpec`, or ``None`` when the
            specification does not know the column.
        rules: The profile's validation rules that apply to this sheet's entity;
            only those naming ``column`` contribute.

    Returns:
        The note text, or an empty string when there is nothing to say.
    """
    if column == "_parent":
        return PARENT_NOTE
    if field is None:
        return ""

    naming = [rule for rule in rules if column in _fields_named_by(rule)]
    constraints = getattr(field, "constraints", None)

    def declared(name: str) -> Any:
        """The field's own value for a constraint, else the first rule's."""
        own = getattr(constraints, name, None) if constraints else None
        if own is not None:
            return own
        return next(
            (getattr(r, name) for r in naming if getattr(r, name, None) is not None),
            None,
        )

    parts: list[str] = []
    description = (getattr(field, "description", "") or "").strip()
    if description:
        parts.append(description)

    lines = [_summary(field)]

    patterns = _unique(
        [getattr(constraints, "pattern", None) if constraints else None]
        + [rule.pattern for rule in naming]
    )
    lines += [f"Pattern: {pattern}" for pattern in patterns]

    length = _bounds(declared("min_length"), declared("max_length"), " characters")
    if length:
        lines.append(f"Length: {length}")
    value_range = _bounds(declared("minimum"), declared("maximum"))
    if value_range:
        lines.append(f"Range: {value_range}")
    items = _bounds(declared("min_items"), declared("max_items"))
    if items:
        lines.append(f"Number of values: {items}")

    allowed = getattr(field, "options", None) or declared("enum")
    if allowed:
        lines.append(f"Allowed values: {_listed(allowed)}")

    ontologies = getattr(field, "ontologies", None)
    if ontologies:
        lines.append(f"Ontologies: {', '.join(ontologies)}")
    within = getattr(field, "within", None)
    if within:
        lines.append(f"Terms under: {within}")

    reference = getattr(field, "reference", None) or next(
        (rule.reference for rule in naming if rule.reference), None
    )
    if reference:
        lines.append(f"Must match: {reference}")
    unique_within = getattr(field, "unique_within", None) or next(
        (rule.unique_within for rule in naming if rule.unique_within), None
    )
    if unique_within:
        lines.append(f"Unique: {_UNIQUE_WORDS.get(unique_within, unique_within)}")

    rule_texts = _unique([(rule.description or rule.name).strip() for rule in naming])
    if rule_texts:
        lines.append(f"Rules: {'; '.join(rule_texts)}")

    parts.append("\n".join(lines))
    return "\n\n".join(parts)


def note_height(note: str) -> int:
    """A comment box height, in points, that shows the whole note."""
    lines = sum(
        max(1, math.ceil(len(line) / _CHARS_PER_LINE)) for line in note.splitlines()
    )
    return max(120, min(640, 24 + 16 * lines))


def _summary(field: Any) -> str:
    """Required or optional, the type in words, the unit and the example."""
    facts = ["Required" if getattr(field, "required", False) else "Optional"]
    kind = _type_words(field)
    if kind:
        facts.append(kind)
    unit = getattr(field, "unit", None)
    if unit:
        facts.append(f"Unit: {unit}")
    example = getattr(field, "example", None)
    if example:
        facts.append(f"Example: {example}")
    return " · ".join(facts)


def _type_words(field: Any) -> str:
    """The field's type as a reader would say it; empty for entity-holding fields."""
    field_type = getattr(field, "type", None)
    if field_type == FieldType.LIST:
        items = getattr(field, "items", None)
        if items is None or items in PRIMITIVE_TYPES:
            return "List of values separated by commas"
        return ""
    return _TYPE_WORDS.get(field_type, "")


def _fields_named_by(rule: Any) -> set[str]:
    """Every field a rule mentions, wherever in the rule it is mentioned."""
    named = {
        name
        for name in (
            rule.field,
            rule.start_field,
            rule.end_field,
            rule.lat_field,
            rule.lon_field,
        )
        if name
    }
    if rule.condition:
        named.update(_IDENTIFIER.findall(rule.condition))
    if rule.when is not None:
        named.update(_predicate_fields(rule.when))
    named.update(rule.require or [])
    return named


def _predicate_fields(predicate: Any) -> Iterable[str]:
    """The fields a predicate tests, through its groups."""
    if hasattr(predicate, "field"):
        yield predicate.field
    for member in (
        getattr(predicate, "all", None) or getattr(predicate, "any", None) or []
    ):
        yield from _predicate_fields(member)
    negated = getattr(predicate, "not_", None)
    if negated is not None:
        yield from _predicate_fields(negated)


def _bounds(low: Any, high: Any, suffix: str = "") -> str:
    """``2 to 8``, ``at least 2`` or ``at most 8``; empty when neither is set."""
    if low is not None and high is not None:
        return f"{_number(low)} to {_number(high)}{suffix}"
    if low is not None:
        return f"at least {_number(low)}{suffix}"
    if high is not None:
        return f"at most {_number(high)}{suffix}"
    return ""


def _number(value: Any) -> str:
    """``-90.0`` as ``-90``, ``0.5`` as ``0.5``."""
    return f"{value:g}" if isinstance(value, float) else str(value)


def _listed(values: Sequence[Any]) -> str:
    """The first values, and how many more the dropdown holds."""
    shown = ", ".join(str(value) for value in values[:MAX_LISTED_VALUES])
    rest = len(values) - MAX_LISTED_VALUES
    return f"{shown} and {rest} more, see the dropdown" if rest > 0 else shown


def _unique(values: Iterable[Any]) -> list[Any]:
    """Set values in first-seen order."""
    seen: list[Any] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen
