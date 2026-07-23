"""Docs CI gate: every ``metaseed`` import shown in the docs must resolve.

Guards against issue #139 F6b — architecture/API pages that import symbols which
no longer exist (``AsyncDatasetRepository``, ``AppStateAdapter``,
``create_metaseed_app``, moved modules, …). Walks every fenced ``python`` block
across ``docs/**/*.md``, and for each ``import metaseed…`` / ``from metaseed…``
statement asserts the module imports and every named symbol is present.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _import_statements() -> list[tuple[str, str]]:
    """Return ``(doc_path, import_source_line)`` for every metaseed import."""
    found: list[tuple[str, str]] = []
    for md in sorted(_DOCS.rglob("*.md")):
        rel = str(md.relative_to(_DOCS))
        for block in _FENCE.findall(md.read_text()):
            try:
                tree = ast.parse(block)
            except SyntaxError:
                continue  # illustrative pseudo-code, not runnable
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "metaseed"
                ):
                    names = ", ".join(a.name for a in node.names)
                    found.append((rel, f"from {node.module} import {names}"))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("metaseed"):
                            found.append((rel, f"import {alias.name}"))
    return found


_STATEMENTS = _import_statements()


@pytest.mark.parametrize(
    ("doc", "statement"),
    _STATEMENTS,
    ids=[f"{d}::{s}" for d, s in _STATEMENTS],
)
def test_doc_import_resolves(doc: str, statement: str) -> None:
    if statement.startswith("import "):
        module = statement.removeprefix("import ").strip()
        importlib.import_module(module)
        return

    module_part, _, names_part = statement.partition(" import ")
    module_name = module_part.removeprefix("from ").strip()
    module = importlib.import_module(module_name)
    for name in (n.strip() for n in names_part.split(",")):
        assert hasattr(module, name), (
            f"{doc}: `{statement}` — {module_name!r} has no attribute {name!r}"
        )
