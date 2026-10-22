"""A breadcrumb stays on one line; a long crumb is shortened, the current one is not.

Long labels ("Investigation: Drought related flowering in Arabidopsis") wrapped
each crumb onto two lines and broke the current record's name mid-word.
"""

from __future__ import annotations

import re

from metaseed.ui.app import STATIC_DIR


def _rule(css: str, selector: str) -> str:
    match = re.search(rf"(?m)^{re.escape(selector)} \{{([^}}]*)\}}", css)
    assert match, f"no rule for {selector}"
    return match.group(1)


def test_crumbs_do_not_wrap_and_shorten_with_an_ellipsis() -> None:
    css = (STATIC_DIR / "css" / "style.css").read_text()

    item = _rule(css, ".breadcrumb-item")
    assert "white-space: nowrap" in item
    assert "text-overflow: ellipsis" in item
    assert "flex-shrink: 0" in _rule(css, ".breadcrumb-item.active")
