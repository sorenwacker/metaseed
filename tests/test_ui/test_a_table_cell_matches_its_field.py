"""A table cell gets the same control as the field it holds.

`field.html` renders a `date` field as a date control and a `datetime` field as
a datetime one. The inline table rendered every cell as a plain text input, so
the Health-RI catalogue's `modification_date` was a picker on the entity form
and a raw string -- "2026-06-01 09:00:00+00:00" -- in the Dataset table. The
same value, typed one way and chosen the other.

The column's type reaches the template: `build_inline_tables` carries
`column_types`. Both cases are checked against shipped profiles, since the
Health-RI profile is a user spec CI cannot see:

- ISA's ``Investigation.studies`` holds ``submission_date`` (``date``),
- miappe's ``Investigation.studies`` holds ``start_date`` (``datetime``).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "metaseed"
    / "ui"
    / "templates"
    / "partials"
    / "inline_table.html"
)


def _root_form(profile: str, version: str) -> str:
    """The root entity's edit form, which carries its children's tables."""
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get(f"/load-example/{profile}/{version}")
    root = next(n for n in state.nodes_by_id.values() if not n.parent_id)
    return client.get(f"/form/{root.entity_type}/{root.id}").text


def _cell_input_type(html: str, column: str) -> str:
    """The input type rendered for one inline-table column."""
    match = re.search(
        rf'<input type="([a-z-]+)"[^>]*name="{re.escape(column)}"[^>]*'
        rf'data-testid="inline-cell-[^"]*-{re.escape(column)}"',
        html,
        re.DOTALL,
    )
    assert match, f"no inline-table cell rendered for {column!r}"
    return match.group(1)


def test_a_date_column_is_a_date_control() -> None:
    """ISA declares submission_date as `date`."""
    html = _root_form("isa", "1.0")

    assert _cell_input_type(html, "submission_date") == "date", (
        "a date column was a text box in the table while the form gave it a picker"
    )


def test_a_datetime_column_is_a_datetime_control() -> None:
    """miappe declares start_date as `datetime` -- the case that showed a raw
    "2026-06-01 09:00:00+00:00" in the table."""
    html = _root_form("miappe", "1.2")

    assert _cell_input_type(html, "start_date") == "datetime-local"


def test_a_text_column_is_still_a_text_box() -> None:
    html = _root_form("miappe", "1.2")

    assert _cell_input_type(html, "title") == "text"


def test_no_stale_date_pattern_survives_on_a_native_control() -> None:
    """A native date input ignores pattern and placeholder; leaving them reads
    as a rule that is no longer enforced anywhere."""
    template = TEMPLATE.read_text()

    assert "YYYY-MM-DD" not in template
    assert r"\d{4}-\d{2}-\d{2}" not in template
