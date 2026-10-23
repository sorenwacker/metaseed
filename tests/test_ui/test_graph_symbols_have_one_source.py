"""Each entity type's colour and shape come from one table, assigned in one place.

prepareGraphData numbered the types present in the data and renderGraphLegend
renumbered every profile type, so a type's nodes and its legend entry had
different symbols (CombinedSample: indigo square nodes, amber legend).
"""

from __future__ import annotations

import re

from metaseed.ui.app import STATIC_DIR

SCRIPT = (STATIC_DIR / "js" / "graph.js").read_text()


def _body(name: str) -> str:
    start = SCRIPT.index(f"function {name}(")
    following = re.search(r"\n\}\n", SCRIPT[start:])
    assert following
    return SCRIPT[start : start + following.end()]


def test_symbols_are_assigned_once_from_one_ordering() -> None:
    calls = re.findall(r"assignEntityDisplay\(([^)]*)\)", SCRIPT)
    # The definition and one call.
    assert calls.count("entityTypes") == 1
    assert [c for c in calls if c != "entityTypes"] == ["displayOrder(data"]
    assert "assignEntityDisplay(displayOrder(data))" in _body("prepareGraphData")


def test_the_legend_reads_the_same_ordering() -> None:
    legend = _body("renderGraphLegend")
    assert "displayOrder(data)" in legend
    assert "assignEntityDisplay" not in legend
