"""The explorer page keeps no colour of its own.

The page carried a table of colours per diff state and painted nodes from it,
so when the legend and the server changed to "green means the two agree" the
canvas stayed on the old scheme, and the filter checkboxes, which matched edges
by hex colour, hid the wrong edges. The server now sends complete styling and a
state per edge; the shared graph script draws it and nothing else. A hex literal
in that script, or a per-state table in the template, is the fork coming back.
"""

import re

from fastapi.testclient import TestClient

from metaseed.specs.merge.models import DiffType
from metaseed.ui.app import STATIC_DIR, TEMPLATES_DIR, create_app

EXPLORE_TEMPLATE = TEMPLATES_DIR / "explore" / "index.html"
GRAPH_SCRIPT = STATIC_DIR / "js" / "explore-graph.js"


def test_the_template_has_no_colour_table_per_diff_state() -> None:
    template = EXPLORE_TEMPLATE.read_text()
    for state in [d.value for d in DiffType] + ["regular"]:
        assert not re.search(rf"\b{state}:\s*\{{", template), state
    assert "DIFF_COLORS" not in template
    assert "SPEC_BUILDER_COLORS" not in template


def test_the_graph_script_has_no_colour_literal() -> None:
    script = GRAPH_SCRIPT.read_text()
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", script)
    for name in ("buildGraphData", "buildNodeConfig", "edgeIsVisible"):
        assert f"function {name}(" in script, name


def test_the_page_links_the_graph_script_and_the_app_serves_it() -> None:
    client = TestClient(create_app())
    page = client.get("/explore/").text
    assert "/static/js/explore-graph.js" in page
    assert client.get("/static/js/explore-graph.js").status_code == 200
