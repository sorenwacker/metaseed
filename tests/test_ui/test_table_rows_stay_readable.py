"""An inline table row stays one readable line of data.

Three defects in the same rows, all visible in the Health-RI catalogue:

- The actions cell was `display: flex`, which takes a `<td>` out of table
  layout. It stopped at its own content height, so the delete button sat at the
  top of a 200px row with empty space beneath it.
- A row was as tall as its longest value: a 70-character note wrapped to seven
  lines, and a narrow column turned "Example University Medical Centre" into a
  four-line ribbon.
- A table wider than its card was cut off at the right edge, taking the actions
  column with it, with nothing to say the rest was there.

These are style rules with no behaviour to assert through a route, so the
stylesheet is read directly — as tests/test_specs/test_merge/test_visualizer.py
and tests/test_ui/test_spec_builder.py already do.
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


def test_the_actions_cell_fills_its_row() -> None:
    declarations = _rule(".row-actions")

    assert "display: flex" not in declarations, (
        "a flex td leaves the rest of a tall row empty below the buttons"
    )
    assert "vertical-align: middle" in declarations
    assert "text-align: center" in declarations


def test_a_long_value_does_not_make_the_whole_row_tall() -> None:
    declarations = _rule(".inline-data-table .cell-display")

    assert "-webkit-line-clamp: 2" in declarations, (
        "a seven-line note made every cell in the row seven lines tall"
    )
    assert "overflow: hidden" in declarations


def test_a_column_cannot_collapse_into_a_ribbon() -> None:
    declarations = _rule(".inline-data-table th,\n.inline-data-table td")

    assert "min-width: 18ch" in declarations, (
        "nineteen columns squeezed into the card left every value as "
        "'http://publi…'; a column needs enough width to say something"
    )


def test_a_wide_table_takes_the_width_it_needs() -> None:
    """Nineteen columns are not made to fit the card: the card scrolls."""
    declarations = _rule(".inline-data-table")

    assert "width: max-content" in declarations
    assert "min-width: 100%" in declarations, (
        "a narrow table should still fill its card"
    )


def test_editing_a_cell_fills_it() -> None:
    """The input took the browser's default twenty characters, so editing a
    wide column meant typing into a small box floating inside it."""
    declarations = _rule(".editable-cell.editing .cell-input")

    assert "width: 100%" in declarations


def test_the_actions_stay_reachable_when_the_table_scrolls() -> None:
    declarations = _rule(
        ".inline-data-table th:last-child,\n.inline-data-table td.row-actions"
    )

    assert "position: sticky" in declarations
    assert "right: 0" in declarations, (
        "the actions column was the first thing cut off by a wide table"
    )
