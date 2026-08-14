"""Every showNotification call passes (message, type) — the defined order.

The only definition (mcp.js) takes (message, type). core.js called it as
(type, message) at seven sites, so toasts displayed the literal word 'error'
as their text and used the real message as a CSS class. There is no JS test
harness, so this scan is the gate for the convention.
"""

from __future__ import annotations

import re
from pathlib import Path

JS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui" / "static" / "js"
)

TYPE_FIRST = re.compile(r"showNotification\(\s*'(?:error|success|info|warning)'\s*,")


def test_no_call_passes_the_type_first() -> None:
    offenders = []
    for path in sorted(JS_DIR.glob("*.js")):
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            if TYPE_FIRST.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, (
        "showNotification takes (message, type); these pass the type first:\n"
        + "\n".join(offenders)
    )
