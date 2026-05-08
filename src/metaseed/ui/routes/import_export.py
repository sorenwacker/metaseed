"""Export routes for data transfer.

Provides routes for exporting data to Excel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import StreamingResponse
from starlette.requests import Request

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
