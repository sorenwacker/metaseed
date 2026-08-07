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

import functools
import json
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from metaseed.ui.state import AppState

# Short timeout for the /seek liveness probe (project list): a misconfigured or
# unreachable SEEK must not stall the page for the client's full request timeout.
_PROBE_TIMEOUT = 5.0


def _safe_filename(name: str) -> str:
    """ASCII-slug a dataset name for a Content-Disposition filename (no injection)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return slug or "dataset"


def register_seek_routes(  # noqa: C901
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

    def _load_profile_named(name: str, version: str = "") -> Any:
        """Load a profile by name and version.

        A blank name is the active dataset's profile. A blank version is the
        latest available, preserving the previous behaviour for callers that do
        not care; a given version is loaded as asked, so a profile with several
        versions can be provisioned at the one a dataset was built on rather than
        only its newest.
        """
        from metaseed.profiles import ProfileFactory
        from metaseed.specs.loader import SpecLoader

        name = (name or "").strip()
        if not name:
            return _load_profile(get_state())
        resolved = (version or "").strip() or ProfileFactory().get_latest_version(name)
        if resolved is None:
            raise ValueError(f"Unknown profile: {name}")
        return SpecLoader(profile=name).load_profile(resolved, name)

    def _model_preview(name: str, version: str = "") -> Any:
        """The browsable Sample-Type/Extended-Metadata projection, or None.

        Degrades to None (the panel simply hides) if the profile cannot be
        loaded or projected, so a preview failure never breaks the page.
        """
        try:
            from metaseed.seek.preview import build_model_preview

            return build_model_preview(_load_profile_named(name, version))
        except Exception:
            return None

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

        # Best-effort project list (needs a reachable, configured SEEK). Uses a
        # short timeout so a misconfigured/unreachable instance can't stall.
        projects: list[tuple[str, str]] = []
        try:
            from metaseed.seek import client_from_settings

            probe = client_from_settings(seek_config, timeout=_PROBE_TIMEOUT)
            projects = probe.list_projects()
        except Exception:  # not configured / unreachable / httpx absent
            projects = []

        from metaseed.profiles import ProfileFactory
        from metaseed.ui.datasets import get_current_dataset_name

        factory = ProfileFactory()
        profiles = factory.list_profiles()
        profile_versions = {p: factory.list_versions(p) for p in profiles}

        context: dict[str, Any] = {
            "base_url": base_url,
            "profile": facade.profile,
            "version": facade.version,
            "profiles": profiles,
            "profile_versions": profile_versions,
            "preview": _model_preview(facade.profile, facade.version),
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

    async def _render(request: Request, **extra: Any) -> HTMLResponse:
        """Build the (blocking) template context off the event loop and render."""
        context = await run_in_threadpool(functools.partial(_context, request, **extra))
        return templates.TemplateResponse(request, "seek/index.html", context)

    @app.get("/seek", response_class=HTMLResponse)
    async def seek_page(request: Request) -> HTMLResponse:
        """Render the SEEK page (export preview + provision/sync panels)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)
        return await _render(request)

    @app.get("/seek/preview", response_class=HTMLResponse)
    async def seek_preview(
        request: Request, profile: str = "", version: str = ""
    ) -> HTMLResponse:
        """Render just the model-preview panel for a profile/version (HTMX).

        Lets the profile/version dropdowns refresh the browsable Sample Types and
        Extended Metadata without a full page load or any write to SEEK.
        """
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)
        preview = await run_in_threadpool(_model_preview, profile, version)
        return templates.TemplateResponse(
            request,
            "seek/_preview.html",
            {"preview": preview, "profile": profile, "version": version},
        )

    @app.post("/seek/provision", response_class=HTMLResponse)
    async def seek_provision(
        request: Request,
        project_id: str = Form(""),
        profile: str = Form(""),
        version: str = Form(""),
    ) -> HTMLResponse:
        """Provision Controlled Vocabularies + Sample Types from a chosen profile."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        client, error = _seek_client(request)
        if client is None:
            return await _render(request, action_error=error)

        def work() -> Any:
            from metaseed.seek.provision import (
                build_provisioning_plan,
                execute_provisioning_plan,
            )

            pid = project_id or client.default_project_id()
            plan = build_provisioning_plan(_load_profile_named(profile, version))
            return execute_provisioning_plan(client, plan, project_id=pid)

        try:
            result = await run_in_threadpool(work)
        except Exception as exc:
            return await _render(request, action_error=f"Provisioning failed: {exc}")
        return await _render(
            request, provision_result=result, provisioned_profile=profile or None
        )

    @app.post("/seek/sync", response_class=HTMLResponse)
    async def seek_sync(request: Request, project_id: str = Form("")) -> HTMLResponse:
        """Push the loaded dataset to SEEK (Investigations/Studies/Assays/Samples)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        state = get_state()
        if not state.entity_tree:
            return await _render(request, action_error="No dataset loaded to sync.")
        client, error = _seek_client(request)
        if client is None:
            return await _render(request, action_error=error)

        def work() -> Any:
            from metaseed.seek.provision import resolve_cv_ids
            from metaseed.seek.sync import sync_dataset_to_seek

            pid = project_id or client.default_project_id()
            profile = _load_profile(state)
            # Sample Types are created per Assay during the walk (a stream chains
            # them), so only the Controlled Vocabularies come from provisioning.
            return sync_dataset_to_seek(
                client,
                _facade_client(state),
                project_id=pid,
                cv_ids=resolve_cv_ids(client, profile),
            )

        try:
            result = await run_in_threadpool(work)
        except Exception as exc:
            return await _render(request, action_error=f"Sync failed: {exc}")
        return await _render(request, sync_result=result)

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
        except Exception:
            return HTMLResponse("Could not build the SEEK RDF.", status_code=500)

        stem = _safe_filename(get_current_dataset_name(state) or "dataset")
        return Response(
            turtle,
            media_type="text/turtle",
            headers={"Content-Disposition": f'attachment; filename="{stem}-seek.ttl"'},
        )

    @app.get("/seek/isa-templates")
    async def seek_isa_templates(
        request: Request, profile: str = "", version: str = ""
    ) -> Response:
        """Download a profile's ISA Templates (for the admin template upload).

        SEEK's ISA-JSON exporter reads each Sample Type's Template to tell an
        assay data file from an assay material, so a dataset cannot be exported
        until an administrator has installed these under *Templates -> populate*.
        """
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        from metaseed.seek.templates import to_isa_template_json

        try:
            spec = _load_profile_named(profile, version)
        except ValueError:
            # Do NOT echo the (attacker-controllable) profile value into HTML.
            return HTMLResponse("Unknown profile requested.", status_code=400)
        try:
            document = to_isa_template_json(spec)
        except Exception:
            return HTMLResponse("Could not build the ISA templates.", status_code=500)

        stem = _safe_filename(profile or get_state().get_or_create_facade().profile)
        return Response(
            json.dumps(document, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}-isa-templates.json"'
            },
        )

    @app.get("/seek/model-ttl")
    async def seek_model_ttl(
        request: Request, profile: str = "", version: str = ""
    ) -> Response:
        """Download a profile's model-only TTL (for the admin Extended Metadata flow)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        try:
            from metaseed.seek.fairds import to_fair_data_station_model_rdf
        except ModuleNotFoundError:
            return HTMLResponse(
                "SEEK export needs rdflib: pip install 'metaseed[seek]'.",
                status_code=503,
            )
        try:
            spec = _load_profile_named(profile, version)
        except ValueError:
            # Do NOT echo the (attacker-controllable) profile value into HTML.
            return HTMLResponse("Unknown profile requested.", status_code=400)
        try:
            turtle = to_fair_data_station_model_rdf(spec)
        except Exception:
            return HTMLResponse("Could not build the model TTL.", status_code=500)

        stem = _safe_filename(profile or get_state().get_or_create_facade().profile)
        return Response(
            turtle,
            media_type="text/turtle",
            headers={"Content-Disposition": f'attachment; filename="{stem}-model.ttl"'},
        )
