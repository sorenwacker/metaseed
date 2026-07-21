"""Routes for the SEEK adapter — export the current dataset for FAIRDOM-SEEK.

Gated by the plugin feature switch: both handlers 404 unless the ``seek`` adapter
is enabled on the Plugins page. The export produces RDF that SEEK ingests with
its own built-in "Import from FAIR Data Station" feature (no external tool).
"""

from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.ui.state import AppState


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
        """Render the SEEK export page (404 when the plugin is disabled)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)
        return templates.TemplateResponse(
            request, "seek/index.html", {"base_url": base_url}
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

        from metaseed import MetaseedClient
        from metaseed.seek.fairds import to_fair_data_station_rdf
        from metaseed.ui.datasets import get_current_dataset_name

        facade = state.get_or_create_facade()
        client = MetaseedClient(facade.profile, facade.version)
        client._facade = facade  # reuse the UI's populated dataset
        turtle = to_fair_data_station_rdf(client)

        name = get_current_dataset_name(state) or "dataset"
        return Response(
            turtle,
            media_type="text/turtle",
            headers={"Content-Disposition": f'attachment; filename="{name}-seek.ttl"'},
        )
