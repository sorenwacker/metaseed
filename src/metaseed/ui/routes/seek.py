"""Routes for the SEEK adapter — export, provision a model, and sync data.

Gated by the plugin feature switch: every handler 404s unless the ``seek`` adapter
is enabled on the Plugins page. Three capabilities:

- **export** (``/seek/isa-rdf``) — download FAIR Data Station RDF for SEEK's own
  import, and (``/seek/model-ttl``) a model-only TTL for the admin Extended
  Metadata flow;
- **provision** (``POST /seek/provision``) — create Controlled Vocabularies +
  Sample Types in SEEK from the active profile (Phase 1);
- **sync** (``POST /seek/sync``) — push the loaded dataset as Investigations,
  Studies, Assays and Samples (Phase 2).

The provision/sync handlers talk to SEEK over its JSON:API using the URL + API
key configured on the Plugins page.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.ui.state import AppState


def _safe_filename(name: str) -> str:
    """ASCII-slug a dataset name for a Content-Disposition filename (no injection)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return slug or "dataset"


def register_seek_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register the SEEK export/provision/sync routes."""

    def _enabled(request: Request) -> bool:
        enabled: bool = request.app.state.settings.adapter_enabled("seek")
        return enabled

    def _facade_client(state: AppState) -> Any:
        """Wrap the UI's populated facade in a MetaseedClient (no spec reload)."""
        from metaseed.api.client import MetaseedClient

        client = MetaseedClient.__new__(MetaseedClient)
        client._facade = state.get_or_create_facade()
        return client

    def _seek_client(request: Request) -> tuple[Any, str | None]:
        """Build a SEEK API client from settings; return ``(client, error)``."""
        config = request.app.state.settings.get_adapter_config("seek")
        try:
            from metaseed.seek import client_from_settings
        except ModuleNotFoundError:
            return None, "SEEK API access needs httpx: pip install 'metaseed[seek]'."
        try:
            return client_from_settings(config), None
        except ValueError as exc:
            return None, str(exc)

    def _load_profile(state: AppState) -> Any:
        from metaseed.specs.loader import SpecLoader

        facade = state.get_or_create_facade()
        return SpecLoader().load_profile(facade.version, facade.profile)

    def _context(request: Request, **extra: Any) -> dict[str, Any]:
        """Shared template context: export preview + SEEK config + projects."""
        state = get_state()
        facade = state.get_or_create_facade()
        settings = request.app.state.settings
        seek_config = settings.get_adapter_config("seek")

        try:
            from metaseed.seek.fairds import exportable_entity_types

            client = _facade_client(state)
            exported: frozenset[str] | None = exportable_entity_types(client)
        except Exception:
            exported = None

        counts = Counter(node.entity_type for node in state.nodes_by_id.values())
        emit_counts = sorted(
            (etype, n)
            for etype, n in counts.items()
            if exported is None or etype in exported
        )

        # Best-effort project list (needs a reachable, configured SEEK).
        projects: list[tuple[str, str]] = []
        seek_client, _seek_error = _seek_client(request)
        if seek_client is not None:
            try:
                projects = seek_client.list_projects()
            except Exception:  # unreachable / unauthorized — leave empty
                projects = []

        from metaseed.ui.datasets import get_current_dataset_name

        context: dict[str, Any] = {
            "base_url": base_url,
            "profile": facade.profile,
            "version": facade.version,
            "dataset_name": get_current_dataset_name(state),
            "entity_count": len(state.nodes_by_id),
            "exportable_count": sum(n for _, n in emit_counts),
            "entity_counts": emit_counts,
            "seek_url": seek_config.get("url", ""),
            "api_key_configured": bool(seek_config.get("api_key")),
            "projects": projects,
            "provision_result": None,
            "sync_result": None,
            "action_error": None,
        }
        context.update(extra)
        return context

    @app.get("/seek", response_class=HTMLResponse)
    async def seek_page(request: Request) -> HTMLResponse:
        """Render the SEEK page (export preview + provision/sync panels)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)
        return templates.TemplateResponse(request, "seek/index.html", _context(request))

    @app.post("/seek/provision", response_class=HTMLResponse)
    async def seek_provision(
        request: Request, project_id: str = Form("")
    ) -> HTMLResponse:
        """Provision Controlled Vocabularies + Sample Types from the profile."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        client, error = _seek_client(request)
        if client is None:
            return templates.TemplateResponse(
                request, "seek/index.html", _context(request, action_error=error)
            )
        from metaseed.seek.provision import (
            build_provisioning_plan,
            execute_provisioning_plan,
        )

        try:
            pid = project_id or client.default_project_id()
            plan = build_provisioning_plan(_load_profile(get_state()))
            result = execute_provisioning_plan(client, plan, project_id=pid)
        except Exception as exc:
            return templates.TemplateResponse(
                request,
                "seek/index.html",
                _context(request, action_error=f"Provisioning failed: {exc}"),
            )
        return templates.TemplateResponse(
            request, "seek/index.html", _context(request, provision_result=result)
        )

    @app.post("/seek/sync", response_class=HTMLResponse)
    async def seek_sync(request: Request, project_id: str = Form("")) -> HTMLResponse:
        """Push the loaded dataset to SEEK (Investigations/Studies/Assays/Samples)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        state = get_state()
        if not state.entity_tree:
            return templates.TemplateResponse(
                request,
                "seek/index.html",
                _context(request, action_error="No dataset loaded to sync."),
            )
        client, error = _seek_client(request)
        if client is None:
            return templates.TemplateResponse(
                request, "seek/index.html", _context(request, action_error=error)
            )
        from metaseed.seek.provision import resolve_sample_type_ids
        from metaseed.seek.sync import sync_dataset_to_seek

        try:
            pid = project_id or client.default_project_id()
            profile = _load_profile(state)
            sample_type_ids = resolve_sample_type_ids(client, profile, project_id=pid)
            result = sync_dataset_to_seek(
                client,
                _facade_client(state),
                project_id=pid,
                sample_type_ids=sample_type_ids,
            )
        except Exception as exc:
            return templates.TemplateResponse(
                request,
                "seek/index.html",
                _context(request, action_error=f"Sync failed: {exc}"),
            )
        return templates.TemplateResponse(
            request, "seek/index.html", _context(request, sync_result=result)
        )

    @app.get("/seek/isa-rdf")
    async def seek_isa_rdf(request: Request) -> Response:
        """Download the current dataset as SEEK-importable ISA RDF (Turtle)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        state = get_state()
        if not state.entity_tree:
            return HTMLResponse(
                "No dataset loaded — build or load a dataset first.", status_code=400
            )
        from metaseed.ui.datasets import get_current_dataset_name

        try:
            from metaseed.seek.fairds import to_fair_data_station_rdf
        except ModuleNotFoundError:
            return HTMLResponse(
                "SEEK export needs rdflib: pip install 'metaseed[seek]'.",
                status_code=503,
            )
        try:
            turtle = to_fair_data_station_rdf(_facade_client(state))
        except Exception as exc:
            return HTMLResponse(f"Could not build SEEK RDF: {exc}", status_code=500)

        stem = _safe_filename(get_current_dataset_name(state) or "dataset")
        return Response(
            turtle,
            media_type="text/turtle",
            headers={"Content-Disposition": f'attachment; filename="{stem}-seek.ttl"'},
        )

    @app.get("/seek/model-ttl")
    async def seek_model_ttl(request: Request) -> Response:
        """Download the profile's model-only TTL (for the admin Extended Metadata flow)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        try:
            from metaseed.seek.fairds import to_fair_data_station_model_rdf
        except ModuleNotFoundError:
            return HTMLResponse(
                "SEEK export needs rdflib: pip install 'metaseed[seek]'.",
                status_code=503,
            )
        state = get_state()
        try:
            turtle = to_fair_data_station_model_rdf(_load_profile(state))
        except Exception as exc:
            return HTMLResponse(f"Could not build model TTL: {exc}", status_code=500)

        stem = _safe_filename(state.get_or_create_facade().profile)
        return Response(
            turtle,
            media_type="text/turtle",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}-model.ttl"'
            },
        )
