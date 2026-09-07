"""A template's placeholder cells are prompts, not data.

A workbook written for someone to fill in carries `<unique_id>`-style cells
saying what belongs there. Importing one unedited must not store the prompt: a
Study whose title is the literal string `<title>` is worse than a Study with no
title, because nothing downstream can tell it is missing.

Angle-bracketed text is treated as a placeholder wherever it appears, which is
the rule the hub's own parser applied before this moved here. A value that is
genuinely `<unknown>` is indistinguishable from a prompt and is dropped with
them; a partly-bracketed value like `<em>x</em>` is data and is kept.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook

from metaseed.ui.services.import_excel import workbook_to_payload
from metaseed.ui.state import AppState

HEADER = ["unique_id", "title", "description"]


def _workbook(*rows: tuple[Any, ...]) -> bytes:
    """A minimal export-shaped workbook: one entity sheet, header, then rows."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Investigation"
    ws.append(HEADER)
    for row in rows:
        ws.append(list(row))
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _entities(*rows: tuple[Any, ...]) -> list[dict[str, Any]]:
    state = AppState(profile="miappe", version="1.1")
    payload = workbook_to_payload(
        _workbook(*rows),
        profile="miappe",
        version="1.1",
        facade=state.get_or_create_facade(),
    )
    return payload["entities"]


def test_a_placeholder_row_is_not_an_entity():
    entities = _entities(
        ("<unique_id>", "<title>", "<description>"),
        ("0001", "SEPT1 trial", "a real one"),
    )

    assert len(entities) == 1
    assert entities[0]["unique_id"] == "0001"


def test_a_placeholder_cell_in_a_real_row_is_not_stored():
    """The row is data; the unfilled cell is still a prompt."""
    entities = _entities(("0001", "SEPT1 trial", "<description>"))

    assert entities[0]["title"] == "SEPT1 trial"
    assert "description" not in entities[0], "the prompt was stored as the description"


def test_a_value_that_merely_contains_angle_brackets_is_data():
    entities = _entities(("0001", "<em>SEPT1</em> trial", "a < b and c > d"))

    assert entities[0]["title"] == "<em>SEPT1</em> trial"
    assert entities[0]["description"] == "a < b and c > d"


def test_bracketed_markup_filling_a_whole_cell_is_still_data():
    """The brackets must wrap the cell *and* nothing else inside, or markup
    that happens to open and close a tag would be read as a prompt."""
    entities = _entities(("0001", "<em>SEPT1</em>", "<p>a trial</p>"))

    assert entities[0]["title"] == "<em>SEPT1</em>"
    assert entities[0]["description"] == "<p>a trial</p>"


def test_an_unedited_template_imports_nothing():
    """Every row a prompt means there is no data, and saying so beats
    inventing entities whose every field is a prompt."""
    with pytest.raises(ValueError):
        _entities(("<unique_id>", "<title>", "<description>"))
