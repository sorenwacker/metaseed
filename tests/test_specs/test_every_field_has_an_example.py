"""Every value field of a shipped profile carries an example that fits the field.

The rule is in ``docs/api/schema-specs.md`` (Fields): a field without an example
shows nothing in the hub's field panel or a generated template. A list or entity
field whose items name another entity holds child records, which the profile's
example dataset illustrates, so it carries none.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pytest

from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType, ProfileSpec
from tests.builtin_specs import builtin_only_loader
from tests.test_examples import shipped_profile_versions

_SCALAR_TYPES: dict[FieldType, tuple[type, ...]] = {
    FieldType.STRING: (str,),
    FieldType.INTEGER: (int,),
    FieldType.FLOAT: (int, float),
    FieldType.BOOLEAN: (bool,),
    FieldType.DATE: (str, date),
    FieldType.DATETIME: (str, datetime),
    FieldType.URI: (str,),
    FieldType.ONTOLOGY_TERM: (str,),
}


def holds_a_value(field: FieldSpec, spec: ProfileSpec) -> bool:
    """Whether the field holds a value rather than child records."""
    if field.type in (FieldType.LIST, FieldType.ENTITY):
        return field.items not in spec.entities
    return True


def value_fields(spec: ProfileSpec) -> list[tuple[str, FieldSpec]]:
    """Every (entity name, field) that must carry an example."""
    return [
        (name, field)
        for name, entity in spec.entities.items()
        for field in entity.fields
        if holds_a_value(field, spec)
    ]


def _fits(field: FieldSpec, value: Any) -> str | None:
    """Why ``value`` is not a valid example for ``field``, or None if it is."""
    if field.type == FieldType.LIST:
        if not isinstance(value, list) or not value:
            return "a list field's example is a non-empty list"
        item_type = (
            FieldType(field.items)
            if field.items in FieldType.__members__.values()
            else FieldType.STRING
        )
        inner = FieldSpec(
            name=field.name, type=item_type, constraints=field.constraints
        )
        return next((why for v in value if (why := _fits(inner, v))), None)
    expected = _SCALAR_TYPES[field.type]
    if isinstance(value, bool) and field.type != FieldType.BOOLEAN:
        return "a boolean is not a value of this type"
    if not isinstance(value, expected):
        return f"example {value!r} is not a {field.type.value}"
    if field.type == FieldType.DATE and isinstance(value, str):
        date.fromisoformat(value)
    if field.type == FieldType.DATETIME and isinstance(value, str):
        datetime.fromisoformat(value)
    allowed = field.options or (field.constraints.enum if field.constraints else None)
    if allowed and value not in allowed:
        return f"example {value!r} is not among the allowed values"
    if field.constraints and isinstance(value, str):
        c = field.constraints
        if c.pattern and not re.search(c.pattern, value):
            return f"example {value!r} does not match pattern {c.pattern}"
        if c.min_length is not None and len(value) < c.min_length:
            return "example shorter than min_length"
        if c.max_length is not None and len(value) > c.max_length:
            return "example longer than max_length"
    if (
        field.constraints
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        c = field.constraints
        if c.minimum is not None and value < c.minimum:
            return "example below minimum"
        if c.maximum is not None and value > c.maximum:
            return "example above maximum"
    return None


@pytest.mark.parametrize("profile,version", shipped_profile_versions())
def test_every_value_field_has_an_example(profile: str, version: str) -> None:
    spec = builtin_only_loader(profile).load_profile(version, profile)
    missing = [f"{e}.{f.name}" for e, f in value_fields(spec) if f.example is None]
    assert not missing, (
        f"{profile} {version}: {len(missing)} fields without example: {missing}"
    )


@pytest.mark.parametrize("profile,version", shipped_profile_versions())
def test_every_example_fits_its_field(profile: str, version: str) -> None:
    spec = builtin_only_loader(profile).load_profile(version, profile)
    bad = [
        f"{e}.{f.name}: {why}"
        for e, f in value_fields(spec)
        if f.example is not None and (why := _fits(f, f.example))
    ]
    assert not bad, "\n".join(bad)


def test_child_record_fields_are_exempt() -> None:
    spec = ProfileSpec(
        spec_version="0.6",
        version="1.0",
        name="t",
        root_entity="A",
        entities={
            "A": EntityDefSpec(
                fields=[
                    FieldSpec(name="id", type=FieldType.STRING, example="a-1"),
                    FieldSpec(name="bs", type=FieldType.LIST, items="B"),
                    FieldSpec(name="tags", type=FieldType.LIST, items="string"),
                ]
            ),
            "B": EntityDefSpec(fields=[FieldSpec(name="id", type=FieldType.STRING)]),
        },
    )
    assert [(e, f.name) for e, f in value_fields(spec)] == [
        ("A", "id"),
        ("A", "tags"),
        ("B", "id"),
    ]
