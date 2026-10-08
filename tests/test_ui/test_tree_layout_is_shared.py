"""The tree layout belongs to the shared graph code and to every graph of a spec.

The hub's Builder had a *Tree* toggle in a script of its own; the local Builder
and the Explorer drew the same kind of graph and had none. The toggle is one
function in erd-common.js, which both applications load, and each toolbar that
offers *Layout* offers *Tree* beside it.
See docs/guides/spec-builder.md, *Arranging the Diagram*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui"
SHARED = UI / "static" / "js" / "erd-common.js"
TOOLBARS = [
    UI / "templates" / "spec_builder" / "base.html",
    UI / "templates" / "explore" / "index.html",
]


def test_the_toggle_is_defined_once_in_the_shared_script() -> None:
    definitions = [
        path.name
        for path in sorted((UI / "static" / "js").glob("*.js"))
        if "function toggleHierarchicalLayout" in path.read_text()
    ]

    assert definitions == [SHARED.name]
    assert "hierarchical" in SHARED.read_text()


@pytest.mark.parametrize("toolbar", TOOLBARS, ids=lambda path: path.parent.name)
def test_every_spec_graph_offers_tree_beside_layout(toolbar: Path) -> None:
    page = toolbar.read_text()

    assert 'onclick="autoLayout()"' in page
    assert 'onclick="toggleHierarchicalLayout()"' in page
    assert 'id="btn-hierarchical"' in page
