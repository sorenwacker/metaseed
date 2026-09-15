"""The explorer draws a change on the field's own line, not as two lines.

The server sends every profile's version of a field (`sides`). These gate the
other end.

A change was first drawn the way git draws one: the base version on a `-` line
above the compare version on a `+` line. On this canvas that misreads. The
legend gives `-` and `+` their own meanings -- field removed, field added --
so a field that merely became required looked like one field removed and
another added, and every changed field cost two lines of node height. A change
is now one line carrying the old value and the new one.

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


def test_a_change_is_drawn_on_one_line() -> None:
    """Both sides are read, and both reach the same line."""
    source = GRAPH_SCRIPT.read_text()

    assert "sides[0]" in source and "sides[1]" in source, (
        "the canvas reads at most one side, so a changed field is drawn as "
        "one of its versions"
    )
    assert "fieldChangeLine" in source, (
        "no line builder carries a field's old and new value together"
    )


def test_a_change_is_not_drawn_as_a_removal_and_an_addition() -> None:
    """`-` and `+` are the legend's glyphs for removed and added fields. A
    change drawn as a `-` line above a `+` line spends them on a third meaning
    the legend does not give them, and reads as two fields rather than one."""
    source = GRAPH_SCRIPT.read_text()

    assert "fieldSideLine" not in source, (
        "a changed field is still split into a base line and a compare line, "
        "which reads as one field removed and another added"
    )


def test_an_unchanged_line_is_not_drawn_as_a_change() -> None:
    """A field is "modified" for reasons a line does not carry -- a reworded
    description, another ontology term. Marking those as changed on the canvas
    claims a change the reader cannot see, so the two sides are compared
    first."""
    source = GRAPH_SCRIPT.read_text()

    assert "sidesDiffer" in source, (
        "the canvas marks every modified field as changed even when the type, "
        "required marker and target are identical on both sides"
    )


def test_the_node_is_sized_by_the_lines_it_draws() -> None:
    """The label decides its own height, so a rendering change cannot leave
    the box measured against a count it no longer matches."""
    source = GRAPH_SCRIPT.read_text()

    assert "fields.length * LAYOUT.fieldHeight" not in source, (
        "node height is computed from the field count rather than from the "
        "label, so any field that is not exactly one line mis-sizes the box"
    )


def test_the_panel_shows_the_values_not_only_the_attribute_names() -> None:
    """ "Changed: type, required" names the attributes but never their values."""
    source = PANEL_SCRIPT.read_text()

    assert "sides" in source, (
        "the entity panel lists which attributes changed but not what they "
        "changed from and to"
    )
