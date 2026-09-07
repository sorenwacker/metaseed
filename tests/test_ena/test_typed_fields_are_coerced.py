"""A declared field that is not a string must not receive ENA's raw string.

The Portal reports every column as text. A field the ``ena`` profile types as an
integer, float, boolean or date therefore needs a coercer, or the mapper writes a
string into it: pydantic warns, ``validate()`` is satisfied, and the value only
fails much later at export, where the SRA schema types the element.

The gate is derived from the profile rather than from a hand-kept list, so a new
typed field cannot be added without a coercer.
"""

from __future__ import annotations

import datetime as dt
import warnings
from pathlib import Path

import yaml

from metaseed.ena.mapper import (
    EXPERIMENT_FIELDS,
    FIELD_COERCERS,
    RUN_FIELDS,
    SAMPLE_FIELDS,
    STUDY_FIELDS,
    build_dataset,
)

PROFILE = Path(__file__).parents[2] / "src/metaseed/specs/ena/1.0/profile.yaml"

# ``list`` is the profile's nesting type: those fields hold child entities, not a
# scalar the mapper coerces.
STRUCTURAL_TYPES = {"list", "entity"}


def _declared_scalar_types() -> dict[str, str]:
    """Every non-string scalar field the profile declares, by field name."""
    spec = yaml.safe_load(PROFILE.read_text())
    return {
        field["name"]: field["type"]
        for entity in spec["entities"].values()
        for field in entity.get("fields") or []
        if field.get("type") not in STRUCTURAL_TYPES | {"string", None}
    }


def _mapped_fields() -> set[str]:
    """Every profile field a ``read_run`` column is written to."""
    return {
        field
        for mapping in (STUDY_FIELDS, SAMPLE_FIELDS, EXPERIMENT_FIELDS, RUN_FIELDS)
        for field in mapping.values()
    }


def _run(client) -> dict:
    """The Run's stored data, not its serialization.

    ``serialize()`` renders a date back to an ISO string, which is exactly what a
    raw string would look like — so the type has to be read where it is held.
    """

    def walk(node):
        entity = client.get_entity(node.id)
        if entity.entity_type == "Run":
            return entity
        for child in node.children:
            found = walk(child)
            if found is not None:
                return found
        return None

    entity = next(found for root in client.get_roots() if (found := walk(root)))
    return dict(entity.data or {})


def _row(run_date: str) -> dict[str, str]:
    return {
        "study_accession": "PRJEB10000",
        "sample_accession": "SAMEA001",
        "experiment_accession": "ERX001",
        "run_accession": "ERR001",
        "run_date": run_date,
    }


def test_every_typed_field_the_mapper_writes_has_a_coercer():
    """The gate: a typed field reachable from a column needs a coercer."""
    typed = _declared_scalar_types()
    missing = {
        field: field_type
        for field, field_type in typed.items()
        if field in _mapped_fields() and field not in FIELD_COERCERS
    }
    assert not missing, (
        f"typed fields written from an ENA column with no coercer: {missing}"
    )


def test_a_run_date_reaches_the_field_as_a_date():
    """Stored as the date's own ISO form, having gone through ``date``.

    The entity store normalises a ``date`` back to an ISO string, so the string
    alone does not prove the type. What proves it is that pydantic raises no
    serializer warning for the field — it does when ENA's raw text is written.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run = _run(build_dataset([_row("2024-04-01")]))
    assert run["run_date"] == dt.date(2024, 4, 1).isoformat()
    assert not [w for w in caught if "run_date" in str(w.message)]


def test_a_run_date_with_a_time_part_is_read_and_the_time_dropped():
    run = _run(build_dataset([_row("2010-02-01T00:00:00")]))
    assert run["run_date"] == dt.date(2010, 2, 1).isoformat()


def test_an_unreadable_run_date_is_left_unset_rather_than_written_as_text():
    run = _run(build_dataset([_row("not-a-date")]))
    assert run.get("run_date") is None
