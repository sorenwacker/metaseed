"""Every page shows the same navigation.

Four templates each carried their own copy of the header links and all four had
drifted: Plugins appeared only on the dataset list, Docs was missing from the
builder's start page, and "Builder" pointed at `/spec-builder` on some pages and
`/spec-builder/select` on another. Moving between pages, buttons came and went.

The links live in `partials/global_nav.html` now. This fails if a template
writes its own again.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = (
    Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui" / "templates"
)
PARTIAL = TEMPLATES / "partials" / "global_nav.html"

#: A page carries the header if it has the bar the links sit in.
NAV_CONTAINER = re.compile(
    r'class="[^"]*header-nav[^"]*"|include "partials/global_nav\.html"'
)


def _pages_with_navigation() -> list[Path]:
    return [
        path
        for path in sorted(TEMPLATES.rglob("*.html"))
        if path != PARTIAL and 'include "partials/global_nav.html"' in path.read_text()
    ]


def test_the_partial_exists_and_names_every_section() -> None:
    """A gate over an empty set passes for the wrong reason."""
    assert PARTIAL.exists()
    text = PARTIAL.read_text()
    for label in ("Datasets", "Builder", "Explorer", "Plugins", "Docs"):
        assert f">{label}</a>" in text, f"{label} is missing from the navigation"


def test_pages_use_the_partial() -> None:
    assert _pages_with_navigation(), "no page includes the navigation partial"


def test_no_template_writes_its_own_navigation() -> None:
    offenders = [
        f"{path.relative_to(TEMPLATES)}:{n}"
        for path in sorted(TEMPLATES.rglob("*.html"))
        if path != PARTIAL
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if "nav-btn" in line
    ]

    assert not offenders, (
        "these write their own header links, which is how Plugins came to appear "
        f"on one page and not the others: {offenders}. Include "
        "partials/global_nav.html instead."
    )
