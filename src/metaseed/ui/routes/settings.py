"""Routes for the Plugins settings page (adapter enable/disable feature switch)."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed import adapters
from metaseed.settings import Settings
from metaseed.ui.state import AppState


def _adapter_rows(settings: Settings) -> list[dict[str, Any]]:
    """Build the per-adapter view rows (info + availability + enabled state)."""
    rows: list[dict[str, Any]] = []
    for info in adapters.ADAPTERS:
        rows.append(
            {
                "info": info,
                "available": adapters.is_available(info),
                "enabled": settings.adapter_enabled(info.key),
            }
        )
    return rows


def register_settings_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    _get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register the Plugins settings page and its toggle endpoint.

    Args:
        app: FastAPI application instance.
        templates: Jinja2 templates instance.
        _get_state: Function to get app state (unused; kept for API consistency).
        base_url: Base URL prefix (no trailing slash). Defaults to "".
    """

    def _settings(request: Request) -> Settings:
        store: Settings = request.app.state.settings
        return store

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        """Render the Plugins page listing every adapter with a toggle."""
        return templates.TemplateResponse(
            request,
            "settings/index.html",
            {"adapters": _adapter_rows(_settings(request)), "base_url": base_url},
        )

    @app.post("/settings/adapters/{key}/toggle", response_class=HTMLResponse)
    async def toggle_adapter(request: Request, key: str) -> HTMLResponse:
        """Flip an adapter's enabled state and return its updated toggle row."""
        settings = _settings(request)
        if not adapters.is_known(key):
            return HTMLResponse("Unknown adapter", status_code=404)

        info = adapters.get_adapter(key)
        available = adapters.is_available(info)
        # Only an available adapter can be toggled; unavailable ones stay off.
        if available:
            settings.set_adapter_enabled(key, not settings.adapter_enabled(key))

        return templates.TemplateResponse(
            request,
            "partials/adapter_toggle.html",
            {
                "row": {
                    "info": info,
                    "available": available,
                    "enabled": settings.adapter_enabled(key),
                },
                "base_url": base_url,
            },
        )
