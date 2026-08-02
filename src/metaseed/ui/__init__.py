"""HTMX web interface for Metaseed."""

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from metaseed.ui.spec_filesystem import (
    FilesystemSpecPersistence,
    FilesystemSpecProvider,
)
from metaseed.ui.spec_persistence import SpecPersistence
from metaseed.ui.spec_provider import SpecProvider

if TYPE_CHECKING:
    from metaseed.ui.app import create_app, run_ui

_APP_EXPORTS = frozenset({"create_app", "run_ui"})


def __getattr__(name: str) -> object:
    """Lazily expose the application factory and the server entry point.

    ``metaseed.ui.app`` builds a FastAPI application at import time. Importing
    it from here made every import of a leaf module — ``metaseed.ui.state``
    from the MCP host, ``metaseed.ui.datasets`` from a CLI command — construct
    the whole web app (ADR 004). ``from metaseed.ui import create_app`` still
    works; it loads on access.

    The ASGI application object is deliberately not re-exported: on this package
    the name ``app`` is the submodule, and ``metaseed.ui.app:app`` stays the
    ASGI target.
    """
    if name in _APP_EXPORTS:
        return getattr(importlib.import_module("metaseed.ui.app"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_templates_dir() -> Path:
    """Get the path to metaseed's UI templates directory.

    This allows external apps to include metaseed's templates
    in their Jinja2 environment.

    Returns:
        Path to the templates directory.
    """
    return Path(__file__).parent / "templates"


__all__ = [
    "FilesystemSpecPersistence",
    "FilesystemSpecProvider",
    "SpecPersistence",
    "SpecProvider",
    "create_app",
    "get_templates_dir",
    "run_ui",
]
