"""The explorer's scripts carry a version, so an edit reaches the browser.

The stylesheet has had a cache-busting gate since a CSS change shipped and the
reader kept seeing the old file. The explorer's two scripts had no such gate:
`explore-graph.js` sat at `?v=1` while its contents changed, so a browser that
had loaded the page once drew the old canvas and the change looked like it had
not been made.

This is a regression guard rather than a bug reproduction: it passes on the
code as it stands. It goes red the moment a script is edited without its
version moving -- which is the failure it exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "metaseed"
    / "ui"
    / "templates"
    / "explore"
    / "index.html"
)

SCRIPTS = ("explore-graph.js", "explore-panel.js")


def test_every_explorer_script_is_loaded_with_a_version() -> None:
    page = TEMPLATE.read_text()

    for script in SCRIPTS:
        assert re.search(rf"{re.escape(script)}\?v=\d+", page), (
            f"{script} is loaded without a ?v= query, so a browser that has "
            "the page cached keeps running the previous version of it"
        )


def test_no_explorer_script_is_loaded_unversioned() -> None:
    """A second, unversioned tag would defeat the versioned one."""
    page = TEMPLATE.read_text()

    for script in SCRIPTS:
        for match in re.finditer(rf"{re.escape(script)}([\"'?])", page):
            assert match.group(1) == "?", (
                f"{script} is referenced without a version somewhere on the page"
            )
