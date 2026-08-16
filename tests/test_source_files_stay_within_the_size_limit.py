"""No source file exceeds 1000 lines — as a test, not as prose.

The limit is a project rule that nothing enforced, so it drifted unnoticed:
`validators/dataset.py` was already at 1003 lines when the 260816 review
counted it, and remediation added 15 more before anyone looked. A rule with no
gate erodes; this is the gate.

Tests are excluded deliberately. A long test file is a list of cases, which is
what it should be; a long source file is a module doing several jobs.
"""

from __future__ import annotations

from pathlib import Path

LIMIT = 1000
SOURCE = Path(__file__).resolve().parent.parent / "src" / "metaseed"


def test_no_source_file_exceeds_the_limit() -> None:
    oversized = {
        str(path.relative_to(SOURCE)): len(path.read_text().splitlines())
        for path in sorted(SOURCE.rglob("*.py"))
    }
    offenders = {name: n for name, n in oversized.items() if n > LIMIT}

    assert not offenders, (
        f"files over {LIMIT} lines: {offenders}. Split the module rather than "
        "raising the limit — the rule is what keeps one file from doing "
        "several jobs."
    )
