"""Every element id the embedding guide promises is one the graph reads.

The guide is the contract other applications build against, and it listed two
ids — `graph-spring-length` and `graph-node-distance` — that `graph.js` never
looks up. A host following it would add those inputs and find the spacing
controls silently inert, with nothing to explain why: no error, no warning,
just a slider that does nothing.

Documentation drift is invisible by construction, so it gets a gate rather
than a promise to be careful.
"""

from __future__ import annotations

import re
from pathlib import Path

_GUIDE = Path("docs/guides/embedding-the-graph.md")
_SCRIPT = Path("src/metaseed/ui/static/js/graph.js")

# Rows of the "DOM contract" table: | `id` | purpose |
_ROW = re.compile(r"^\|\s*`([a-z-]+)`\s*\|", re.MULTILINE)


def _documented_ids() -> list[str]:
    contract = _GUIDE.read_text().split("## Supplying the data")[0]
    return _ROW.findall(contract)


def test_the_guide_lists_the_ids_the_script_looks_up() -> None:
    documented = _documented_ids()

    assert documented, "no DOM contract rows parsed; this gate would pass vacuously"

    script = _SCRIPT.read_text()
    missing = [name for name in documented if f"'{name}'" not in script]

    assert missing == [], (
        "the embedding guide promises element ids graph.js never reads, so a host "
        f"following it gets controls that silently do nothing: {missing}"
    )


def test_the_required_element_is_documented() -> None:
    """`graph-view` is the one element without which nothing draws."""
    assert "graph-view" in _documented_ids()


def test_the_graph_refreshes_on_an_inline_cell_edit() -> None:
    """A cell edit posts with hx-swap="none" and fires only the entityChanged
    trigger, no htmx:afterSwap. graph.js must listen to entityChanged as well,
    or a change to a node's label field only reached the graph on reload."""
    script = _SCRIPT.read_text()
    assert "addEventListener('entityChanged'" in script, (
        "graph.js refreshes only on htmx:afterSwap; an inline cell edit (hx-swap="
        '"none") never triggers that, so a label-field change did not redraw the graph'
    )
