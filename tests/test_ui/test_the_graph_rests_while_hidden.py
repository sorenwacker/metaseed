"""The graph must cost nothing while it cannot be seen.

An open graph panel polled `/api/graph` every 2 s whatever the browser was
doing, and each poll made the server reload the whole dataset from disk. A
background tab kept paying that; closing the panel stopped the polling but left
the vis.js simulation running on a canvas nobody could see.

The browser suite is advisory in CI (it never runs on a pull request), so these
source scans are the gate for the behaviour documented under "While the graph is
not visible" in docs/guides/embedding-the-graph.md. The matching browser test is
in tests/test_ui/test_selenium.py.
"""

from __future__ import annotations

import re
from pathlib import Path

JS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui" / "static" / "js"
)
GRAPH_JS = JS_DIR / "graph.js"
CORE_JS = JS_DIR / "core.js"


def _body_of(source: str, declaration: str) -> str:
    """Return the text of a function from its declaration to the next one."""
    start = source.index(declaration)
    next_function = source.find("\nfunction ", start + len(declaration))
    return source[start : next_function if next_function != -1 else len(source)]


def test_a_background_tab_is_not_polled() -> None:
    """The poll checked only the panel's class, so a hidden tab kept fetching."""
    poll = _body_of(CORE_JS.read_text(), "function startGraphPolling(")

    assert "graphIsVisible()" in poll, (
        "the poll must skip a graph that cannot be seen, tab visibility included"
    )


def test_visibility_is_one_answer_for_the_panel_and_the_tab() -> None:
    """Two separate checks are how one of them comes to disagree with the other."""
    visible = _body_of(GRAPH_JS.read_text(), "function graphIsVisible(")

    assert "graph-container" in visible and "hidden" in visible
    assert "visibilityState" in visible, (
        "graphIsVisible must treat a background tab as not visible"
    )


def test_the_tab_going_away_pauses_the_graph() -> None:
    source = GRAPH_JS.read_text()

    assert "visibilitychange" in source, (
        "nothing reacted to the tab being hidden, so polling and physics ran on"
    )
    assert "function pauseGraph(" in source and "function resumeGraph(" in source


def test_pausing_stops_the_simulation_as_well_as_the_polling() -> None:
    """Closing the panel stopped the polling only; the layout kept computing."""
    pause = _body_of(GRAPH_JS.read_text(), "function pauseGraph(")

    assert "stopGraphPolling()" in pause
    assert "stopSimulation()" in pause, (
        "a hidden canvas must not keep running the force simulation"
    )


def test_a_hidden_graph_is_not_redrawn_on_a_theme_change() -> None:
    """The colour-scheme listener reloaded the graph whatever its state."""
    source = GRAPH_JS.read_text()
    listener = source[source.index("prefers-color-scheme") :]
    listener = listener[: listener.index("\n}")]

    assert "graphIsVisible()" in listener


def test_closing_the_panel_pauses_rather_than_only_stopping_the_poll() -> None:
    apply_views = _body_of(GRAPH_JS.read_text(), "function applyViews(")

    assert re.search(r"\}\s*else\s*\{\s*pauseGraph\(\);", apply_views), (
        "applyViews must pause the graph when the panel goes away"
    )
