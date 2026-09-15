"""What acts on a spec sits with the spec, not in the shared header.

The builder put Sidebar, Layout, Preview, Export, Save and New Spec in the
header every page shares, beside the global navigation. They act on one spec
and nothing else, while the row directly below -- "13 entities" and the zoom
controls -- is the spec's own toolbar and had room.

The navigation gate (test_one_navigation.py) guards the links and the bar
itself; this guards where a page's own actions go.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "metaseed"
    / "ui"
    / "templates"
    / "spec_builder"
    / "base.html"
)

#: Every control that acts on the open spec.
ACTIONS = ("toggleSidebar()", "autoLayout()", "showPreview()", "saveSpec()")


def _toolbar(text: str) -> str:
    start = text.index('class="erd-canvas-toolbar"')
    return text[start : text.index("erd-canvas-wrapper", start)]


def _header_block(text: str) -> str:
    start = text.index("{% call header(")
    return text[start : text.index("{% endcall %}", start)]


def test_the_actions_are_in_the_canvas_toolbar() -> None:
    toolbar = _toolbar(TEMPLATE.read_text())

    for action in ACTIONS:
        assert action in toolbar, f"{action} is not with the spec it acts on"
    assert "New Spec" in toolbar
    assert "/spec-builder/export" in toolbar


def test_the_shared_header_carries_none_of_them() -> None:
    header = _header_block(TEMPLATE.read_text())

    for action in ACTIONS:
        assert action not in header, f"{action} is back in the header every page shares"
    assert "btn-header" not in header


def test_the_entity_count_still_leads_the_toolbar() -> None:
    """The count says what is on the canvas; the actions follow it."""
    toolbar = _toolbar(TEMPLATE.read_text())

    assert toolbar.index("canvas-info") < toolbar.index("spec-actions")
    assert "entities" in toolbar
