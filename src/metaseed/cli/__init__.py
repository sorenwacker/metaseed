"""CLI package for Metaseed.

The Typer application and its commands live in :mod:`metaseed.cli.app`; this
package re-exports the ``app`` entry point used by the ``metaseed`` console
script.
"""

from metaseed.cli.app import app

__all__ = ["app"]
