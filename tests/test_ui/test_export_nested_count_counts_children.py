"""A parent's nested-field column counts its actual children, not an empty list.

The export writes one sheet per entity type and links a child to its parent with
a ``_parent`` column; the children never sit embedded in the parent's own data.
So the parent row's nested-field cell (``studies``, ``samples``) must count the
children that hang from it on their own sheet -- reading the parent's embedded
list instead reports 0 for every parent, which is what a user saw: a Study with
four sources, eight observation units and two assays exported as ``0  0  0``.
"""

from __future__ import annotations

from metaseed.api.client import MetaseedClient
from metaseed.ui.services.export import build_workbook_from_facade

_SPEC = {
    "name": "demo",
    "version": "1.0",
    "root_entity": "Investigation",
    "entities": {
        "Investigation": {
            "fields": [
                {"name": "identifier", "type": "string", "description": "d"},
                {
                    "name": "studies",
                    "type": "list",
                    "items": "Study",
                    "description": "d",
                },
            ]
        },
        "Study": {
            "fields": [
                {"name": "study_id", "type": "string", "description": "d"},
                {
                    "name": "samples",
                    "type": "list",
                    "items": "Sample",
                    "description": "d",
                },
            ]
        },
        "Sample": {
            "fields": [{"name": "sample_id", "type": "string", "description": "d"}]
        },
    },
}

_DOC = {
    "identifier": "INV-1",
    "studies": [
        {
            "study_id": "STU-1",
            "samples": [
                {"sample_id": "S-1"},
                {"sample_id": "S-2"},
                {"sample_id": "S-3"},
            ],
        }
    ],
}


def _cell(sheet, header_row, column_name, data_row=2):
    headers = [c.value for c in sheet[header_row]]
    return sheet.cell(row=data_row, column=headers.index(column_name) + 1).value


def _workbook():
    facade = MetaseedClient.from_spec(_SPEC)._facade
    facade.load_nested(_DOC, "Investigation")
    return build_workbook_from_facade(facade)


def test_a_studys_nested_sample_column_shows_the_child_count() -> None:
    wb = _workbook()
    assert _cell(wb["Study"], 1, "samples") == "3"


def test_an_investigations_nested_study_column_shows_the_child_count() -> None:
    wb = _workbook()
    assert _cell(wb["Investigation"], 1, "studies") == "1"


def test_a_parent_with_no_children_of_a_type_shows_zero() -> None:
    facade = MetaseedClient.from_spec(_SPEC)._facade
    facade.load_nested(
        {"identifier": "INV-1", "studies": [{"study_id": "STU-1"}]}, "Investigation"
    )
    wb = build_workbook_from_facade(facade)
    assert _cell(wb["Study"], 1, "samples") == "0"
