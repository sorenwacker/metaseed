"""Routes for the SEEK adapter — export the current dataset for FAIRDOM-SEEK.

Gated by the plugin feature switch: both handlers 404 unless the ``seek`` adapter
is enabled on the Plugins page. The export produces RDF that SEEK ingests with
its own built-in "Import from FAIR Data Station" feature (no external tool).
"""

import re
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
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
    """Register the SEEK export page and its RDF download endpoint."""

    def _enabled(request: Request) -> bool:
        enabled: bool = request.app.state.settings.adapter_enabled("seek")
        return enabled

    @app.get("/seek", response_class=HTMLResponse)
    async def seek_page(request: Request) -> HTMLResponse:
        """Render the SEEK export page with the current profile/dataset context."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        from collections import Counter

        from metaseed.ui.datasets import get_current_dataset_name

        state = get_state()
        facade = state.get_or_create_facade()
        counts = Counter(node.entity_type for node in state.nodes_by_id.values())
        seek_config = request.app.state.settings.get_adapter_config("seek")

        return templates.TemplateResponse(
            request,
            "seek/index.html",
            {
                "base_url": base_url,
                "profile": facade.profile,
                "version": facade.version,
                "dataset_name": get_current_dataset_name(state),
                "entity_count": len(state.nodes_by_id),
                "entity_counts": sorted(counts.items()),
                "seek_url": seek_config.get("url", ""),
            },
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

        from metaseed.api.client import MetaseedClient
        from metaseed.ui.datasets import get_current_dataset_name

        try:
            from metaseed.seek.fairds import to_fair_data_station_rdf
        except ModuleNotFoundError:
            return HTMLResponse(
                "SEEK export needs rdflib: pip install 'metaseed[seek]'.",
                status_code=503,
            )

        # Wrap the UI's populated facade in a client without reloading a spec.
        client = MetaseedClient.__new__(MetaseedClient)
        client._facade = state.get_or_create_facade()
        try:
            turtle = to_fair_data_station_rdf(client)
        except Exception as exc:  # surface generation errors as a readable 500
            return HTMLResponse(f"Could not build SEEK RDF: {exc}", status_code=500)

        stem = _safe_filename(get_current_dataset_name(state) or "dataset")
        return Response(
            turtle,
            media_type="text/turtle",
            headers={"Content-Disposition": f'attachment; filename="{stem}-seek.ttl"'},
        )
