"""Every timestamp this code writes is UTC, and says so.

Naive local timestamps are unorderable against UTC ones: "which copy is newer"
becomes guesswork across a DST change or a machine configured differently.
Dataset metadata carried `datetime.now().isoformat()` — no offset — and export
filenames were stamped with the local date, so a file written at 01:00 CEST was
dated a day ahead of the instant it was written.
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
#: Sample code in docstrings and generated snippets is not a timestamp we write.
EXEMPT_FILES = {"helper.py"}


def _naive_clock_calls(tree: ast.AST) -> list[str]:
    """Calls that read the *process* clock without saying which zone they mean.

    Only the datetime module counts. ``func.now()`` is SQLAlchemy's SQL NOW(),
    evaluated by the database into a TIMESTAMPTZ, which is an instant and not a
    local reading at all.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        base = ast.unparse(node.func.value)
        if base.split(".")[0] not in {"datetime", "date", "dt"}:
            continue
        name = node.func.attr
        if name == "utcnow":
            found.append("datetime.utcnow()")
        elif name in {"now", "today"} and not node.args and not node.keywords:
            found.append(f"{base}.{name}() with no timezone")
    return found


def test_no_naive_clock_reads_in_the_library() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name in EXEMPT_FILES:
            continue
        for call in _naive_clock_calls(ast.parse(path.read_text())):
            offenders.append(f"{path.relative_to(SRC)}: {call}")

    assert not offenders, (
        "these read the clock without a timezone, which records local time with "
        "no offset — use datetime.now(UTC):\n  " + "\n  ".join(offenders)
    )
