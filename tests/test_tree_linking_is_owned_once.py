"""The link/unlink invariant is decided in ONE module (ADR 005).

Three components hand-maintained the parent-child invariant, and the 260814
triage fixed three bugs that were all the same bug: a reference written on
create and forgotten on delete, and the LIST-vs-ENTITY shape decided
differently per component. The decisions live in facade/linking.py; a
repository or store that starts deciding shapes again turns this red.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "metaseed"

#: Where the shape discriminator may appear: its definition, and the one
#: module allowed to decide with it.
ALLOWED = {
    Path("facade") / "helper.py",
    Path("facade") / "linking.py",
}


def test_the_shape_rule_has_one_home() -> None:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        if relative in ALLOWED:
            continue
        if "single_entity_fields" in path.read_text():
            offenders.append(str(relative))
    assert not offenders, (
        f"the LIST-vs-ENTITY shape rule is decided outside facade/linking.py "
        f"in: {offenders} (ADR 005)"
    )
