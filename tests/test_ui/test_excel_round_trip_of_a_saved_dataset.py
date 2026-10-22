"""A saved dataset survives Excel export and import, and rows added in Excel land where they say.

The round-trip test that existed built two entities in memory, one level deep,
and never added a row, so it passed while a real dataset broke: one carrying a
stale copy of its children embedded in its parent came back with every child
twice, and a new row could not say which of two parent types held it. These
build a MIAPPE dataset four levels deep, with entity types held by two parents,
save and reload it as the application does, and fill in the workbook as a
person would.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from typing import Any

import pytest

from metaseed import MetaseedClient
from metaseed.ui.services.export import build_workbook_from_facade
from metaseed.ui.services.import_excel import workbook_to_payload

PROFILE, VERSION = "miappe", "1.2"
BELONGS_TO = "Belongs to"


def _saved_dataset() -> dict[str, Any]:
    """A dataset as the application saves it: built, serialized, written as JSON."""
    c = MetaseedClient(PROFILE, VERSION)
    inv = c.create_entity(
        "Investigation", {"unique_id": "INV-1", "title": "Trial"}, skip_validation=True
    )
    c.create_entity(
        "Person",
        {"name": "Investigation contact"},
        parent_id=inv.id,
        skip_validation=True,
    )
    study = c.create_entity(
        "Study",
        {"unique_id": "STU-1", "investigation_id": "INV-1", "title": "Field study"},
        parent_id=inv.id,
        skip_validation=True,
    )
    c.create_entity(
        "Person", {"name": "Study person"}, parent_id=study.id, skip_validation=True
    )
    c.create_entity(
        "Event",
        {"unique_id": "EV-1", "study_id": "STU-1", "event_type": "sowing"},
        parent_id=study.id,
        skip_validation=True,
    )
    for n in (1, 2):
        ou = c.create_entity(
            "ObservationUnit",
            {"unique_id": f"OU-{n}", "study_id": "STU-1"},
            parent_id=study.id,
            skip_validation=True,
        )
        c.create_entity(
            "Sample", {"unique_id": f"S-{n}"}, parent_id=ou.id, skip_validation=True
        )
    c.create_entity(
        "Event",
        {"unique_id": "EV-2", "study_id": "STU-1", "event_type": "watering"},
        parent_id=ou.id,
        skip_validation=True,
    )
    return json.loads(json.dumps(c.serialize()))


def _client(payload: dict[str, Any]) -> MetaseedClient:
    client = MetaseedClient(PROFILE, VERSION)
    client.load(payload)
    return client


def _workbook(payload: dict[str, Any]) -> Any:
    return build_workbook_from_facade(_client(payload).facade)


def _import(workbook: Any) -> MetaseedClient:
    raw = io.BytesIO()
    workbook.save(raw)
    fresh = MetaseedClient(PROFILE, VERSION)
    payload = workbook_to_payload(
        raw.getvalue(), profile=PROFILE, version=VERSION, facade=fresh.facade
    )
    fresh.load(payload)
    return fresh


def _key(data: dict[str, Any]) -> str:
    return str(data.get("unique_id") or data.get("name"))


def _tree(client: MetaseedClient) -> Counter:
    """Each record with the record and the field that hold it."""
    entities = {e.id: e for e in (client.get_entity(n.id) for n in _all_nodes(client))}
    nodes = {n.id: n for n in _all_nodes(client)}
    edges: Counter = Counter()
    for node_id, entity in entities.items():
        parent = entities.get(entity.parent_id) if entity.parent_id else None
        edges[
            (
                entity.entity_type,
                _key(entity.data),
                parent.entity_type if parent else None,
                _key(parent.data) if parent else None,
                nodes[node_id].parent_field if parent else None,
            )
        ] += 1
    return edges


def _all_nodes(client: MetaseedClient) -> list[Any]:
    out: list[Any] = []

    def walk(node: Any) -> None:
        out.append(node)
        for child in client.get_children(node.id):
            walk(child)

    for root in client.get_roots():
        walk(root)
    return out


def _append(workbook: Any, sheet: str, values: dict[str, str]) -> None:
    ws = workbook[sheet]
    header = [cell.value for cell in ws[1]]
    ws.append([values.get(column) for column in header])


def test_a_saved_dataset_comes_back_as_the_same_tree() -> None:
    saved = _saved_dataset()

    assert _tree(_import(_workbook(saved))) == _tree(_client(saved))


def test_a_stale_embedded_copy_is_not_written_a_second_time() -> None:
    """A parent still carrying an old copy of its children, next to the stored records."""
    saved = _saved_dataset()
    investigation = next(e for e in saved["entities"] if e["_type"] == "Investigation")
    investigation["studies"] = [
        {
            "unique_id": "STU-1",
            "investigation_id": "INV-1",
            "title": "Old title",
            "observation_units": [{"unique_id": "OU-1", "study_id": "STU-1"}],
        }
    ]

    workbook = _workbook(saved)

    studies = [
        row
        for row in workbook["Study"].iter_rows(min_row=2, values_only=True)
        if any(row)
    ]
    units = [
        row
        for row in workbook["ObservationUnit"].iter_rows(min_row=2, values_only=True)
        if any(row)
    ]
    assert len(studies) == 1
    assert len(units) == 2
    assert _tree(_import(workbook)) == _tree(_client(saved))


def test_a_row_added_below_the_table_lands_under_the_record_it_names() -> None:
    workbook = _workbook(_saved_dataset())
    _append(
        workbook, "Sample", {"unique_id": "S-NEW", BELONGS_TO: "ObservationUnit: OU-2"}
    )

    tree = _tree(_import(workbook))

    assert tree[("Sample", "S-NEW", "ObservationUnit", "OU-2", "samples")] == 1


@pytest.mark.parametrize(
    ("belongs_to", "parent", "field"),
    [
        ("Study: STU-1", ("Study", "STU-1"), "persons"),
        ("Investigation: INV-1", ("Investigation", "INV-1"), "contacts"),
    ],
)
def test_a_type_held_by_two_parents_goes_where_the_row_says(
    belongs_to, parent, field
) -> None:
    workbook = _workbook(_saved_dataset())
    _append(workbook, "Person", {"name": "New person", BELONGS_TO: belongs_to})

    tree = _tree(_import(workbook))

    assert tree[("Person", "New person", *parent, field)] == 1


def test_the_export_names_each_parent_by_type_and_identifier() -> None:
    workbook = _workbook(_saved_dataset())
    ws = workbook["Person"]
    header = [cell.value for cell in ws[1]]
    assert "_parent" not in header
    column = header.index(BELONGS_TO)
    values = {
        row[column] for row in ws.iter_rows(min_row=2, values_only=True) if any(row)
    }
    assert values == {"Investigation: INV-1", "Study: STU-1"}


def test_belongs_to_offers_every_record_that_can_hold_the_row() -> None:
    """The Person dropdown covers investigations and studies, from the sheets as they stand."""
    workbook = _workbook(_saved_dataset())
    ws = workbook["Person"]
    letter = chr(ord("A") + [c.value for c in ws[1]].index(BELONGS_TO))
    validation = next(
        dv for dv in ws.data_validations.dataValidation if f"{letter}2" in str(dv.sqref)
    )
    source_sheet, source_range = validation.formula1.split("!")
    source = workbook[source_sheet.strip("'")]
    formulas = " ".join(
        str(cell.value)
        for row in source[source_range.replace("$", "")]
        for cell in row
        if cell.value
    )
    assert "Investigation" in formulas and "Study" in formulas


def test_the_workbook_opens_with_how_to_add_data() -> None:
    workbook = _workbook(_saved_dataset())

    assert workbook.sheetnames[0] == "How to add data"
    text = " ".join(
        str(c)
        for row in workbook["How to add data"].iter_rows(values_only=True)
        for c in row
        if c
    )
    assert "Belongs to" in text and "below" in text


def test_a_workbook_with_the_old_parent_column_still_imports() -> None:
    saved = _saved_dataset()
    workbook = _workbook(saved)
    for ws in workbook.worksheets:
        header = [cell.value for cell in ws[1]]
        if BELONGS_TO not in header:
            continue
        column = header.index(BELONGS_TO) + 1
        ws.cell(row=1, column=column, value="_parent")
        for row in range(2, ws.max_row + 1):
            cell = ws.cell(row=row, column=column)
            if cell.value:
                cell.value = str(cell.value).split(": ", 1)[1]

    assert _tree(_import(workbook)) == _tree(_client(saved))


def test_a_belongs_to_naming_nothing_refuses_the_workbook() -> None:
    workbook = _workbook(_saved_dataset())
    _append(
        workbook, "Sample", {"unique_id": "S-NEW", BELONGS_TO: "ObservationUnit: OU-9"}
    )
    _append(workbook, "Sample", {"unique_id": "S-NEW2", BELONGS_TO: "Study: STU-1"})
    raw = io.BytesIO()
    workbook.save(raw)

    with pytest.raises(ValueError) as refused:
        workbook_to_payload(
            raw.getvalue(),
            profile=PROFILE,
            version=VERSION,
            facade=MetaseedClient(PROFILE, VERSION).facade,
        )

    message = str(refused.value)
    assert "Sample" in message and "OU-9" in message
    assert "Study does not hold Sample" in message
