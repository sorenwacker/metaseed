"""Routes for the Plugins settings page: enable/disable + per-adapter config."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed import adapters
from metaseed.settings import Settings
from metaseed.ui.state import AppState


def run_adapter_check(info: adapters.AdapterInfo, config: dict[str, str]) -> Any:
    """Run the adapter's declared connection check against ``config``.

    A module-level seam so route tests can substitute the outcome without a
    network; the registry's ``check_ref`` decides which function runs.
    """
    return info.resolve_check()(config)


def _row(
    settings: Settings, info: adapters.AdapterInfo, check: Any | None = None
) -> dict[str, Any]:
    """Build one adapter view row: availability, enabled state, stored config,
    and the outcome of a connection check when one was just run."""
    return {
        "info": info,
        "available": adapters.is_available(info),
        "enabled": settings.adapter_enabled(info.key),
        "config": settings.get_adapter_config(info.key),
        "check": check,
    }


def register_settings_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    _get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register the Plugins settings page, its toggle, and its config endpoints."""

    def _settings(request: Request) -> Settings:
        store: Settings = request.app.state.settings
        return store

    def _render_row(
        request: Request, info: adapters.AdapterInfo, check: Any | None = None
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/adapter_toggle.html",
            {"row": _row(_settings(request), info, check), "base_url": base_url},
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        """Render the Plugins page listing every adapter."""
        settings = _settings(request)
        rows = [_row(settings, info) for info in adapters.ADAPTERS]
        return templates.TemplateResponse(
            request, "settings/index.html", {"adapters": rows, "base_url": base_url}
        )

    @app.post("/settings/adapters/{key}/toggle", response_class=HTMLResponse)
    async def toggle_adapter(request: Request, key: str) -> HTMLResponse:
        """Flip an adapter's enabled state and return its updated row."""
        if not adapters.is_known(key):
            return HTMLResponse("Unknown adapter", status_code=404)
        info = adapters.get_adapter(key)
        if adapters.is_available(info):  # unavailable adapters stay off
            settings = _settings(request)
            settings.set_adapter_enabled(key, not settings.adapter_enabled(key))
        return _render_row(request, info)

    @app.post("/settings/adapters/{key}/check", response_class=HTMLResponse)
    async def check_adapter(request: Request, key: str) -> HTMLResponse:
        """Probe the adapter's configured service and return the row with the verdict."""
        if not adapters.is_known(key):
            return HTMLResponse("Unknown adapter", status_code=404)
        info = adapters.get_adapter(key)
        settings = _settings(request)
        if info.check_ref is None or not settings.adapter_enabled(key):
            return HTMLResponse("Adapter has no connection check", status_code=404)
        config = settings.get_adapter_config(key)
        check = await run_in_threadpool(run_adapter_check, info, config)
        return _render_row(request, info, check)

    @app.post("/settings/adapters/{key}/config", response_class=HTMLResponse)
    async def config_adapter(request: Request, key: str) -> HTMLResponse:
        """Save an adapter's configuration and return its updated row."""
        if not adapters.is_known(key):
            return HTMLResponse("Unknown adapter", status_code=404)
        info = adapters.get_adapter(key)
        settings = _settings(request)
        # Only a configurable, enabled adapter accepts config — mirror the UI gate.
        if not info.config_fields or not settings.adapter_enabled(key):
            return _render_row(request, info)

        form = await request.form()
        values: dict[str, str] = {}
        for field in info.config_fields:
            raw = form.get(field.key, "")
            submitted = raw.strip() if isinstance(raw, str) else ""
            # A blank secret means "leave unchanged"; a blank plain field clears it.
            if field.secret and not submitted:
                continue
            values[field.key] = submitted
        settings.set_adapter_config(key, values)
        return _render_row(request, info)
