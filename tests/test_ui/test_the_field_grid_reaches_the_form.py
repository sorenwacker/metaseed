"""The grid styles the form the reader actually sees.

`.field-grid` lays the fields out in columns. A stylesheet rule alone proves
nothing: the class has to be on the element the form renders, or the CSS styles
markup that does not exist and the page keeps one field per row while every
style assertion passes.

It is deliberately not on `.form-section`, which the explorer's panel and the
spec builder's fieldsets also use -- they stack their controls and must keep
doing so.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

TEMPLATES = (
    Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui" / "templates"
)


def _root_form() -> str:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    root = next(n for n in state.nodes_by_id.values() if not n.parent_id)
    return client.get(f"/form/{root.entity_type}/{root.id}").text


def test_the_rendered_form_carries_the_grid_class() -> None:
    html = _root_form()

    assert 'class="form-section field-grid"' in html, (
        "the grid rule styles a class no rendered page has, so the fields keep "
        "flowing at their own width"
    )


def test_the_optional_section_is_laid_out_too() -> None:
    """Its container is the grid's second selector."""
    html = _root_form()

    assert 'class="collapsible-content"' in html


def test_the_shared_section_class_is_not_the_grid() -> None:
    """The explorer's panel and the builder's fieldsets use form-section and
    stack; styling that class turned both into columns."""
    for name in ("explore/index.html", "spec_builder/partials/field_form.html"):
        text = (TEMPLATES / name).read_text()
        assert "field-grid" not in text, f"{name} must keep stacking its controls"


def test_the_stylesheet_targets_that_class() -> None:
    css = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "metaseed"
        / "ui"
        / "static"
        / "css"
        / "style.css"
    ).read_text()

    assert re.search(r"^\.field-grid,\s*$", css, re.MULTILINE), (
        "the grid rule must key on the class the form renders"
    )
