"""The public surface is what the contract says it is, and nothing else.

``docs/specification/api-contract.md`` enumerates the symbols consumers may
import and promises stability for them. That promise is only worth something if
the document and the package cannot drift apart, so this module treats the
document's "Stable surface" table as the snapshot and compares ``__all__``
against it.

The document is the source of truth on purpose. A snapshot copied into a test
would be a third place to update, and the one most easily updated without
thinking -- which is how a symbol becomes public by accident.
"""

from __future__ import annotations

import re
from pathlib import Path

import metaseed

CONTRACT = Path(__file__).parent.parent / "docs" / "specification" / "api-contract.md"

# The section whose table is the promise; other tables in the document describe
# extras and errors, which are not the public symbol list.
SURFACE_HEADING = "### Stable surface"

# Documented in the table but not exported by name: it is the package version
# attribute, which `__all__` does not carry.
NOT_IN_ALL = {"__version__"}


def _documented_symbols() -> set[str]:
    """Every symbol named in the contract's stable-surface table.

    Reads the first column of the table under :data:`SURFACE_HEADING`, where a
    row may name several related symbols (``Entity``, ``EntityNode``, ...).

    Returns:
        The documented symbol names, excluding those `__all__` cannot carry.
    """
    text = CONTRACT.read_text()
    start = text.index(SURFACE_HEADING)
    end = text.index("\n## ", start)
    documented: set[str] = set()
    for line in text[start:end].splitlines():
        if not line.startswith("| `"):
            continue
        first_column = line.split("|")[1]
        documented.update(re.findall(r"`([^`]+)`", first_column))
    return documented - NOT_IN_ALL


def test_the_contract_and_the_package_agree_on_what_is_public() -> None:
    """`__all__` is exactly the documented surface.

    Adding a symbol to `__all__` is a promise to keep it working; removing one
    breaks a consumer. Either is a deliberate act, so either must be written in
    the contract in the same change.
    """
    documented = _documented_symbols()
    exported = set(metaseed.__all__)

    undocumented = sorted(exported - documented)
    unexported = sorted(documented - exported)

    assert not undocumented, (
        "exported from metaseed but absent from the stable-surface table in "
        f"{CONTRACT.name}: {undocumented}. Exporting a symbol promises it will "
        "keep working -- document the promise, or drop it from __all__."
    )
    assert not unexported, (
        f"promised by {CONTRACT.name} but missing from metaseed.__all__: "
        f"{unexported}. A consumer following the contract would get an "
        "ImportError."
    )


def test_every_promised_symbol_actually_resolves() -> None:
    """A name in `__all__` that does not resolve is a broken promise.

    ``from metaseed import *`` raises on such a name, and a consumer importing
    it by name gets an ImportError -- so a stale entry is worse than an
    undocumented one.
    """
    missing = sorted(name for name in metaseed.__all__ if not hasattr(metaseed, name))

    assert not missing, (
        f"named in metaseed.__all__ but not importable from the package: {missing}"
    )


def test_the_documented_import_example_still_works() -> None:
    """The contract shows a `from metaseed import (...)` block; it must run.

    A documented example that no longer imports is a promise already broken at
    the point a reader tries it.
    """
    text = CONTRACT.read_text()
    block = re.search(
        r"```python\nfrom metaseed import \(\n(.*?)\)\n```", text, re.DOTALL
    )
    assert block is not None, (
        f"{CONTRACT.name} no longer contains the `from metaseed import (...)` "
        "example this test verifies; update the test or restore the example."
    )

    names = [
        line.strip().rstrip(",") for line in block.group(1).splitlines() if line.strip()
    ]
    missing = sorted(name for name in names if not hasattr(metaseed, name))

    assert not missing, (
        f"the import example in {CONTRACT.name} names symbols the package does "
        f"not provide: {missing}"
    )
