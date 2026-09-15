"""Form fields fill the width they are given.

`.form-group` was `display: inline-block` with `min-width: 220px`, so fields
flowed at their own width rather than sharing the row: three fields left a gap
wide enough for a fourth, a long URI was truncated in a narrow box while the
space beside it sat empty, and each row started wherever the previous one
happened to end. `.form-textarea` reserved 100px of height whatever the value,
so every list field was a tall box.

Style rules with no behaviour to assert through a route, so the stylesheet is
read directly — as tests/test_ui/test_table_rows_stay_readable.py does.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLESHEET = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "metaseed"
    / "ui"
    / "static"
    / "css"
    / "style.css"
)


def _rule(selector: str) -> str:
    """The declarations of the first rule whose selector list matches exactly."""
    css = STYLESHEET.read_text()
    pattern = rf"(?:^|\}}|\*/)\s*{re.escape(selector)}\s*\{{([^}}]*)\}}"
    match = re.search(pattern, css, re.MULTILINE)
    assert match, f"no rule for {selector!r}"
    return match.group(1)


def test_the_field_sections_share_the_row() -> None:
    declarations = _rule(".field-grid,\n.collapsible-content")

    assert "display: grid" in declarations, (
        "fields flowed at their own width and left the rest of the row empty"
    )
    assert "1fr" in declarations, "a column must take its share of the width"


def test_a_field_does_not_set_its_own_width() -> None:
    declarations = _rule(".form-group")

    assert "display: inline-block" not in declarations
    assert "min-width: 220px" not in declarations, (
        "a fixed minimum is what stopped a field from growing or shrinking"
    )


def test_a_control_fills_its_field() -> None:
    declarations = _rule(".form-group .form-input,\n.form-group .form-textarea")

    assert "width: 100%" in declarations, (
        "a long URI was truncated while the column beside it was empty"
    )


def test_a_table_is_not_squeezed_into_one_column() -> None:
    """A child table spans the row: it has its own width and its own scroll."""
    declarations = _rule(
        ".field-grid > h3,\n"
        ".field-grid > .inline-table-section,\n"
        ".field-grid > .add-child-section,\n"
        ".collapsible-content > .optional-filter,\n"
        ".collapsible-content > .inline-table-section"
    )

    assert "grid-column: 1 / -1" in declarations
