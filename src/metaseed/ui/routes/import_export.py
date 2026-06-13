"""Import and export routes for data transfer.

Provides routes for exporting entity data to Excel and importing a dataset
from an uploaded JSON file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.requests import Request

from ..datasets import import_dataset
from ..services.export import export_to_bytes, generate_filename

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    from ..state import AppState


def register_export_routes(
    app: FastAPI,
    templates: Jinja2Templates,  # noqa: ARG001
    get_state: Callable[[], AppState],
) -> None:
    """Register export routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance (unused, kept for API consistency).
        get_state: Callable returning AppState.
    """

    @app.get("/export")
    async def export_excel(_request: Request) -> StreamingResponse:
        """Export current entity data to Excel file."""
        state = get_state()

        output = export_to_bytes(state)
        filename = generate_filename(state)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def register_import_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
) -> None:
    """Register data import routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance for rendering notifications.
        get_state: Callable returning AppState.
    """

    @app.post("/import")
    async def import_json(request: Request, file: UploadFile) -> HTMLResponse:
        """Import an uploaded JSON dataset file into the current state."""
        state = get_state()
        raw = await file.read()
        try:
            info = import_dataset(state, raw)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "components/notification.html",
                {"type": "error", "message": f"Import failed: {exc}"},
            )

        return templates.TemplateResponse(
            request,
            "components/notification.html",
            {
                "type": "success",
                "message": (
                    f"Imported {info['entity_count']} entities "
                    f"from profile '{info['profile']}'"
                ),
            },
        )
