"""HTMX route handlers for the UI.

Provides FastAPI routes with Jinja2 templates for the HTMX-based interface.

This module assembles routes from domain-specific modules in the routes/ package.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    register_settings_routes,
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
    from metaseed.agent.mcp.context import MCPContext
    from metaseed.repositories.memory import MemoryEntityRepository
    from metaseed.ui.dataset_manager import DatasetManagerFactory
    from metaseed.ui.datasets import auto_save
    from metaseed.ui.services.entities import EntityService

    app = FastAPI(title="Metaseed")

    if state is None:
        state = AppState()

    app.state.ui_state = state
    app.state.base_url = base_url

    from metaseed.settings import Settings

    app.state.settings = Settings()

    # Create dataset manager factory with default filesystem repository
    dataset_factory = DatasetManagerFactory()

    # Create entity service factory that always uses current facade
    def get_entity_service() -> EntityService:
        return EntityService(MemoryEntityRepository(state, on_change=auto_save))

    # Create MCP context with all dependencies
    context = MCPContext(
        state=state,
        get_entity_service=get_entity_service,
        dataset_factory=dataset_factory,
    )
    app.state.mcp_context = context

    # Install the shared MCP context only once the app starts serving — never at
    # construction. A module-level `app = create_app()` (used by uvicorn) runs at
    # import; doing set_context() there would hijack the standalone MCP server's
    # state simply because something imported `metaseed.ui`.
    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        from metaseed.agent.mcp.server import set_context

        set_context(context)
        yield

    app.router.lifespan_context = _lifespan

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Add global template variables
    try:
        from metaseed._version import __version__
    except ImportError:
        __version__ = "0.0.0+unknown"

    templates.env.globals["app_version"] = __version__
    templates.env.globals["base_url"] = base_url

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
        ui_state: AppState = app.state.ui_state
        return ui_state

    def get_base_url() -> str:
        base_url_value: str = app.state.base_url
        return base_url_value

    # Mount spec builder routes
    from .spec_builder import create_spec_builder_router

    spec_builder_router = create_spec_builder_router(
        templates, get_state, base_url=base_url
    )
    app.include_router(spec_builder_router)

    # Register all route modules
    register_core_routes(app, templates, get_state, base_url=base_url)
    register_form_routes(app, templates, get_state)
    register_entity_crud_routes(app, templates, get_state, base_url=base_url)
    register_table_routes(app, templates, get_state)
    register_nested_routes(app, templates, get_state)
    register_export_routes(app, templates, get_state)
    register_import_routes(app, templates, get_state)
    register_validation_routes(app, templates, get_state)
    register_example_routes(app, get_state)
    register_api_routes(app, get_state)
    register_explore_routes(app, templates, get_state, base_url=base_url)
    register_settings_routes(app, templates, get_state, base_url=base_url)

    from .routes.dcat import register_dcat_routes

    register_dcat_routes(app, get_state)

    return app


app = create_app()


def run_ui(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the Metaseed web interface."""
    import uvicorn

    from metaseed.logging import configure_logging

    configure_logging(level="INFO")
    logger.info("Starting Metaseed UI at http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
