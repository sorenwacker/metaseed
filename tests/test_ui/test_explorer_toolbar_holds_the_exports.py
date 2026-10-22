"""The explorer's view controls and exports share the canvas toolbar.

They were split three ways: Layout, Tree and Fit in the page header, zoom over
the canvas, PNG and the reports at the foot of the sidebar. The hub puts them in
one bar over the canvas; the standalone explorer now does the same.
"""

from __future__ import annotations

from metaseed.ui.app import TEMPLATES_DIR

PAGE = (TEMPLATES_DIR / "explore" / "index.html").read_text(encoding="utf-8")


def _toolbar() -> str:
    start = PAGE.index('<div class="erd-canvas-toolbar">')
    return PAGE[start : PAGE.index('<div class="erd-canvas-wrapper">', start)]


def test_every_control_and_export_is_in_the_canvas_toolbar() -> None:
    bar = _toolbar()
    for control in (
        "zoomIn()",
        "fitGraph()",
        "autoLayout()",
        "toggleHierarchicalLayout()",
        "ERD.exportPng(",
        "exportReport('markdown')",
        "exportReport('csv')",
        "exportReport('xlsx')",
    ):
        assert control in bar, control


def test_nothing_is_left_in_the_header_or_the_sidebar() -> None:
    outside = PAGE.replace(_toolbar(), "")
    assert "autoLayout()" not in outside
    assert "exportReport(" not in outside.split("<script")[0]
