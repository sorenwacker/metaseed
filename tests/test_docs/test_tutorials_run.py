"""Every tutorial page runs as written (261126).

A tutorial is a sequence of ``python`` blocks that build on each other. The
blocks of one page are executed in order in one namespace, so a renamed method
or a changed field fails here instead of on a reader's machine. Each tutorial
must also be in the site navigation, or MkDocs publishes it unlinked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs"
TUTORIALS = sorted((DOCS / "tutorials").glob("*.md"))
_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def test_there_are_tutorials() -> None:
    assert {p.name for p in TUTORIALS} >= {"client.md", "facade.md"}


@pytest.mark.parametrize("page", TUTORIALS, ids=lambda p: p.name)
def test_tutorial_runs_in_order(
    page: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    blocks = _FENCE.findall(page.read_text())
    assert blocks, f"{page.name} has no python blocks"
    namespace: dict[str, object] = {"__name__": "__tutorial__"}
    for number, block in enumerate(blocks, start=1):
        try:
            exec(compile(block, f"{page.name}[block {number}]", "exec"), namespace)  # noqa: S102
        except Exception as exc:
            pytest.fail(f"{page.name}, block {number} failed: {exc!r}")


def test_every_tutorial_is_in_the_navigation() -> None:
    mkdocs = (DOCS.parent / "mkdocs.yml").read_text()
    missing = [
        f"tutorials/{p.name}"
        for p in TUTORIALS
        if not re.search(
            rf":\s*tutorials/{re.escape(p.name)}\s*$", mkdocs, re.MULTILINE
        )
    ]
    assert not missing, f"tutorials missing from the mkdocs nav: {missing}"
