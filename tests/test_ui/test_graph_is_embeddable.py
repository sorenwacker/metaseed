"""graph.js must be usable by an application that is not metaseed (#254).

The drawing — legend, per-type counts, click-to-hide filtering — is the piece
downstream applications kept reimplementing, and a lesser copy is how the two
drift. Reuse failed on transport, not on drawing: the endpoint was
`BASE_URL + '/api/graph'` with no way for a host to say which dataset, and
nothing drew the graph on an ordinary page load, so an embedder got a blank
canvas and no error.

There is no JS test harness in this project, so these scans are the gate for
the embedding contract documented in docs/guides/embedding-the-graph.md.
"""

from __future__ import annotations

from pathlib import Path

GRAPH_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "metaseed"
    / "ui"
    / "static"
    / "js"
    / "graph.js"
)


def _source() -> str:
    return GRAPH_JS.read_text()


def test_the_endpoint_is_configurable_at_call_time() -> None:
    """A host sets the URL after the script has loaded, so it must be read late."""
    source = _source()

    assert "METASEED_GRAPH_URL" in source
    assert "function loadGraph(url)" in source, (
        "loadGraph must accept an explicit URL override"
    )


def test_drawing_is_reachable_without_the_fetch() -> None:
    """A host with its own transport hands the data over directly."""
    source = _source()

    assert "function renderGraphData(" in source
    assert "window.renderGraphData" in source, (
        "the drawing entry point must be reachable from a host page"
    )


def test_the_graph_draws_itself_on_a_plain_page_load() -> None:
    """Without this an embedder gets an empty canvas and no error."""
    source = _source()

    assert "DOMContentLoaded" in source
    assert "METASEED_GRAPH_AUTOLOAD" in source, (
        "a host managing its own draw must be able to suppress the automatic one"
    )


def test_the_contract_is_documented() -> None:
    docs = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "guides"
        / "embedding-the-graph.md"
    ).read_text()

    for name in ("graph-view", "renderGraphData", "METASEED_GRAPH_URL"):
        assert name in docs
