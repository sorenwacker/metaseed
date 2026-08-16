"""`__all__` must name only what exists (260816 review).

`metaseed.api.__all__` still listed "app" after the REST application was
deleted, so `from metaseed.api import *` raised AttributeError — the one thing
`__all__` exists to make safe. Nothing in this repository star-imports it,
which is why nothing noticed; a consumer doing so is exactly who it breaks.
"""

from __future__ import annotations

import importlib


def test_every_exported_name_exists() -> None:
    module = importlib.import_module("metaseed.api")

    missing = [name for name in module.__all__ if not hasattr(module, name)]

    assert not missing, f"__all__ promises names that do not exist: {missing}"


def test_a_star_import_succeeds() -> None:
    namespace: dict[str, object] = {}

    exec("from metaseed.api import *", namespace)  # noqa: S102

    assert "MetaseedClient" in namespace
