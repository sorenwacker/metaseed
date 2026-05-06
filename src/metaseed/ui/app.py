"""HTMX route handlers for the UI.

Provides FastAPI routes with Jinja2 templates for the HTMX-based interface.

This module assembles routes from domain-specific modules in the routes/ package.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import (
    register_api_routes,
    register_core_routes,
    register_entity_crud_routes,
    register_example_routes,
    register_explore_routes,
    register_export_routes,
    register_form_routes,
    register_import_routes,
    register_nested_routes,
    register_table_routes,
    register_validation_routes,
)
from .state import AppState

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"


def create_app(state: AppState | None = None, base_url: str = "") -> FastAPI:
    """Create the FastAPI application with HTMX routes.

    Args:
        state: Optional initial state. Creates new state if not provided.
        base_url: Base URL prefix for the application (e.g., "/hub").
            Should not have a trailing slash. Defaults to empty string.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="Metaseed")

    if state is None:
        state = AppState()

    app.state.ui_state = state
    app.state.base_url = base_url

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def format_display(value: Any) -> str:
        """Format a value for display in table cells."""
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v)
        if isinstance(value, str) and value.strip() in ("[]", ""):
            return ""
        return str(value)

    templates.env.filters["display"] = format_display

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def get_state() -> AppState:
        return app.state.ui_state

    def get_base_url() -> str:
        return app.state.base_url

    # Mount spec builder routes
    from .spec_builder import create_spec_builder_router

    spec_builder_router = create_spec_builder_router(templates, get_state, base_url=base_url)
    app.include_router(spec_builder_router)

    # Register all route modules
    register_core_routes(app, templates, get_state, base_url=base_url)
    register_form_routes(app, templates, get_state)
    register_entity_crud_routes(app, templates, get_state)
    register_table_routes(app, templates, get_state)
    register_nested_routes(app, templates, get_state)
    register_export_routes(app, templates, get_state)
    register_import_routes(app, templates, get_state)
    register_validation_routes(app, templates, get_state)
    register_example_routes(app, get_state)
    register_api_routes(app, get_state)
    register_explore_routes(app, templates, get_state, base_url=base_url)

    return app


app = create_app()


def run_ui(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the Metaseed web interface."""
    import uvicorn

    from metaseed.logging import configure_logging

    configure_logging(level="INFO")
    logger.info("Starting Metaseed UI at http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
