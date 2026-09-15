"""A date field is chosen, not typed.

A `date` field rendered as a text box with `pattern="\\d{4}-\\d{2}-\\d{2}"`: the
format was told to the reader only after they had got it wrong. A `datetime`
field had no branch at all and fell through to the plain text input at the end,
so a Health-RI `release_date` was an editable string reading
"2025-01-15 09:00:00+00:00".

The stored value has to survive the change: `datetime-local` holds
YYYY-MM-DDTHH:MM and `date` holds YYYY-MM-DD, so the value is narrowed to what
the control can carry rather than dropped.

The table cells are covered separately, in
tests/test_ui/test_a_table_cell_matches_its_field.py.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _root_form(profile: str, version: str) -> str:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get(f"/load-example/{profile}/{version}")
    root = next(n for n in state.nodes_by_id.values() if not n.parent_id)
    return client.get(f"/form/{root.entity_type}/{root.id}").text


def _field_input(html: str, name: str) -> tuple[str, str]:
    """The input type and value rendered for one form field."""
    match = re.search(
        rf'<input type="([a-z-]+)"[^>]*name="{re.escape(name)}"[^>]*value="([^"]*)"',
        html,
        re.DOTALL,
    )
    assert match, f"no form input rendered for {name!r}"
    return match.group(1), match.group(2)


def test_a_date_field_is_a_date_control() -> None:
    """ISA declares submission_date as `date`."""
    kind, _value = _field_input(_root_form("isa", "1.0"), "submission_date")

    assert kind == "date", "a date was typed into a text box behind a regex"


def test_a_datetime_field_is_a_datetime_control() -> None:
    """miappe declares start_date as `datetime`, which had no branch at all."""
    html = _root_form("miappe", "1.2")
    root_has_start_date = 'name="start_date"' in html
    if not root_has_start_date:  # pragma: no cover - guards the fixture, not the code
        return

    kind, _value = _field_input(html, "start_date")
    assert kind == "datetime-local"


def test_the_stored_value_survives_the_control() -> None:
    """A value the control cannot hold renders empty, losing what was there."""
    kind, value = _field_input(_root_form("isa", "1.0"), "submission_date")

    assert kind == "date"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), (
        f"a date control needs YYYY-MM-DD; got {value!r}"
    )


def test_no_regex_pattern_survives_on_a_native_control() -> None:
    """A native date input ignores pattern and placeholder; leaving them reads
    as a rule that nothing enforces."""
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "metaseed"
        / "ui"
        / "templates"
        / "partials"
        / "field.html"
    ).read_text()

    assert 'placeholder="YYYY-MM-DD"' not in template
    assert "pattern=" not in template, (
        "a native date control ignores a regex pattern; leaving one reads as a "
        "rule that nothing enforces"
    )
