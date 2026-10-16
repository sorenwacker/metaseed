"""The local test runs exclude the same markers as CI.

`make test`, the pre-push hook, the CI `test` job and the release gate each
spell the marker expression. They drifted (`make test` and the hook also
excluded `ui`), so a green local run and a green CI run could mean different
test sets. Each place is compared here against the CI job's expression.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _markers(text: str, anchor: str) -> str:
    """The first ``-m "..."`` expression after ``anchor`` in ``text``."""
    start = text.index(anchor)
    match = re.search(r'-m\s+"([^"]+)"', text[start:])
    assert match, f"no -m expression after {anchor!r}"
    return match.group(1)


def _ci() -> str:
    return _markers((ROOT / ".github/workflows/ci.yml").read_text(), "uv run pytest")


@pytest.mark.parametrize(
    ("where", "expression"),
    [
        (
            "Makefile `test`",
            lambda: _markers((ROOT / "Makefile").read_text(), "\ntest:"),
        ),
        (
            "release gate",
            lambda: _markers(
                (ROOT / ".github/workflows/release.yml").read_text(), "pytest tests/"
            ),
        ),
        (
            "pre-push hook",
            lambda: re.search(
                r'MARKERS = "([^"]+)"', (ROOT / "scripts/pre_push_tests.py").read_text()
            ).group(1),
        ),
    ],
    ids=["makefile", "release", "pre-push"],
)
def test_the_marker_expression_matches_ci(
    where: str, expression: Callable[[], str]
) -> None:
    assert expression() == _ci(), f"{where} excludes different markers than CI"
