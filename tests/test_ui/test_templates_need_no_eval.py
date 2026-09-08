"""No template may need `eval`, or fetch a script or stylesheet from elsewhere.

These pages are served by two applications. Standalone, metaseed sends no
Content-Security-Policy and anything works. The hub serves the same markup under
`script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'`, and there
each of these fails silently in production while every test stays green:

* `hx-headers` and `hx-vals` are evaluated by htmx with `new Function`, so the
  request raises `EvalError` and is abandoned. `hx-headers` sat on `<body>` in
  four templates, which meant every request; users could not create entities.
* a script or stylesheet from another origin is simply not loaded -- htmx from
  unpkg, or the webfonts, which were imported from Google while the files sat
  unused in this repository.

The `hx-headers` here set `X-Requested-With`, which nothing in this project
reads, so it was removed rather than reimplemented; the hub sets its own headers
for every request on its pages, including the CSRF token it does read. Values
belong in `hx-include`, which evaluates nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "src" / "metaseed" / "ui" / "templates"
CSS = ROOT / "src" / "metaseed" / "ui" / "static" / "css"

EVAL_ATTRIBUTES = ("hx-headers", "hx-vals")


def _templates() -> list[Path]:
    return sorted(TEMPLATES.rglob("*.html"))


def test_there_are_templates_to_check() -> None:
    """A gate over an empty set passes for the wrong reason."""
    assert _templates()


@pytest.mark.parametrize("attribute", EVAL_ATTRIBUTES)
def test_no_template_uses_an_attribute_htmx_evaluates(attribute: str) -> None:
    pattern = re.compile(rf"\b{re.escape(attribute)}\s*=")
    offenders = [
        f"{path.relative_to(TEMPLATES)}:{n}"
        for path in _templates()
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if pattern.search(line)
    ]

    assert not offenders, (
        f"{attribute} is evaluated by htmx with new Function, which a strict "
        f"Content-Security-Policy blocks, so the request never happens: "
        f"{offenders}. Use an htmx:configRequest listener or hx-include."
    )


@pytest.mark.xfail(
    reason=(
        "htmx and vis-network are loaded from unpkg. These templates are served "
        "standalone, where no policy applies, so this is not the production "
        "failure the rest of this module covers -- but it makes the pages "
        "unusable under any strict policy and depends on a third party being up. "
        "Vendoring both is its own change; see the issue linked in the changelog."
    ),
    strict=True,
)
def test_no_template_loads_a_script_from_another_origin() -> None:
    """A cross-origin script is blocked by `script-src 'self'`."""
    pattern = re.compile(r"<script[^>]+src=[\"']https?://", re.IGNORECASE)
    offenders = [
        f"{path.relative_to(TEMPLATES)}:{n}"
        for path in _templates()
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if pattern.search(line)
    ]

    assert not offenders, (
        f"a script from another origin does not load under script-src 'self', "
        f"so the page runs without it: {offenders}. Vendor the file instead."
    )


def test_no_stylesheet_imports_a_webfont_from_another_origin() -> None:
    """`style-src 'self'` blocks the import, and the faces are served here."""
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(CSS.glob("*.css"))
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if "@import" in line and "http" in line
    ]

    assert not offenders, (
        f"an imported stylesheet from another origin is blocked by "
        f"style-src 'self': {offenders}. Serve the font files from here."
    )
