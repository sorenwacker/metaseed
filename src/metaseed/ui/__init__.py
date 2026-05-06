"""HTMX web interface for Metaseed."""

from pathlib import Path

from metaseed.ui.app import app, create_app, run_ui
from metaseed.ui.spec_filesystem import FilesystemSpecPersistence, FilesystemSpecProvider
from metaseed.ui.spec_persistence import SpecPersistence
from metaseed.ui.spec_provider import SpecProvider


def get_templates_dir() -> Path:
    """Get the path to metaseed's UI templates directory.

    This allows external apps to include metaseed's templates
    in their Jinja2 environment.

    Returns:
        Path to the templates directory.
    """
    return Path(__file__).parent / "templates"


__all__ = [
    "app",
    "create_app",
    "get_templates_dir",
    "run_ui",
    "SpecPersistence",
    "SpecProvider",
    "FilesystemSpecPersistence",
    "FilesystemSpecProvider",
]
