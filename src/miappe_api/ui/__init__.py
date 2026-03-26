"""HTMX web interface for MIAPPE-API."""

from miappe_api.ui.routes import app, create_app, run_ui

__all__ = ["app", "create_app", "run_ui"]
