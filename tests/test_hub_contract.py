"""Every symbol the hub imports from metaseed still resolves (#70).

The hub is the sole external consumer, and 'check ../metaseed-hub before
renaming a public symbol' was an informal rule. This is that rule as a test:
the inventory in tests/hub_contract.py is generated from the hub's actual
imports (scripts/regenerate_hub_contract.py), and a rename or deletion of
anything on it turns metaseed's OWN CI red — before a release ships the
break to the hub.
"""

from __future__ import annotations

import importlib

import pytest

from tests.hub_contract import HUB_IMPORTS

_CASES = [
    (module, symbol)
    for module, symbols in sorted(HUB_IMPORTS.items())
    for symbol in symbols
] + [(module, None) for module, symbols in sorted(HUB_IMPORTS.items()) if not symbols]


@pytest.mark.parametrize(
    ("module", "symbol"),
    _CASES,
    ids=[f"{m}.{s}" if s else m for m, s in _CASES],
)
def test_the_hub_used_symbol_resolves(module: str, symbol: str | None) -> None:
    imported = importlib.import_module(module)
    if symbol is None:
        return
    if hasattr(imported, symbol):
        return
    # `from metaseed import adapters` imports a SUBMODULE, which is not an
    # attribute of the package until something imports it.
    try:
        importlib.import_module(f"{module}.{symbol}")
    except ModuleNotFoundError:
        raise AssertionError(
            f"metaseed-hub imports {symbol!r} from {module}; renaming or "
            "removing it breaks the hub. Change the hub first, then "
            "regenerate tests/hub_contract.py."
        ) from None
