"""The explorer draws a changed field as a diff, not as one of its versions.

The server sends every profile's version of a field (`sides`). These gate the
other end: the canvas script has to read them and draw the base prefixed `-`
and the compare prefixed `+`, and the node has to be sized by the lines it
actually draws -- a two-line field under a height computed from the field
*count* is a label clipped by its own box.

There is no JS test harness in this repository, so these read the source.
"""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui" / "static"
GRAPH_SCRIPT = STATIC / "js" / "explore-graph.js"
PANEL_SCRIPT = STATIC / "js" / "explore-panel.js"


def test_the_canvas_reads_both_sides_of_a_field() -> None:
    source = GRAPH_SCRIPT.read_text()

    assert "sides" in source, (
        "the canvas still renders a single version per field, so a changed "
        "field cannot show what it changed from"
    )


def test_the_canvas_draws_a_base_line_and_a_compare_line() -> None:
    """Both sides are read, not just whichever the server put first."""
    source = GRAPH_SCRIPT.read_text()

    assert "sides[0]" in source and "sides[1]" in source, (
        "the canvas reads at most one side, so a changed field is drawn as "
        "one of its versions"
    )


def test_an_unchanged_line_is_not_drawn_as_a_change() -> None:
    """A field is "modified" for reasons a line does not carry -- a reworded
    description, another ontology term. Splitting those into "- x: string"
    over "+ x: string" claims a change the reader cannot see and doubles the
    node's height to say nothing, so the two sides are compared first."""
    source = GRAPH_SCRIPT.read_text()

    assert "sidesDiffer" in source, (
        "the canvas splits every modified field into two lines even when the "
        "type, required marker and target are identical on both sides"
    )


def test_the_node_is_sized_by_the_lines_it_draws() -> None:
    """A field can now occupy two lines, so counting fields under-sizes the box."""
    source = GRAPH_SCRIPT.read_text()

    assert "fields.length * LAYOUT.fieldHeight" not in source, (
        "node height is still computed from the field count, so a node with "
        "two-line fields is drawn too short for its own label"
    )


def test_the_panel_shows_the_values_not_only_the_attribute_names() -> None:
    """ "Changed: type, required" names the attributes but never their values."""
    source = PANEL_SCRIPT.read_text()

    assert "sides" in source, (
        "the entity panel lists which attributes changed but not what they "
        "changed from and to"
    )
