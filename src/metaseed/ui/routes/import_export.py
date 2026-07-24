"""Import and export routes for data transfer.

Provides routes for exporting entity data to Excel and importing a dataset
from an uploaded JSON file.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

from fastapi import HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.requests import Request

from metaseed import adapters

from ..datasets import import_dataset
from ..services.export import export_to_bytes, generate_filename

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    from ..state import AppState


def export_options_for_profile(profile: str) -> list[dict[str, str]]:
    """Return ``[{key, label, surface}]`` adapter-export options for a profile.

    Derived from the adapter registry (:mod:`metaseed.adapters`) — the
    ``export``-kind actions — so a new exporter is offered in the UI by declaring
    it there, not by editing this route. ``surface`` lets the template group the
    buttons.
    """
    return [
        {"key": action.key, "label": action.label, "surface": action.surface}
        for action in adapters.actions_for_profile(profile, kind="export")
    ]


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

    @app.get("/export/adapter/{fmt}")
    async def export_adapter(fmt: str, _request: Request) -> StreamingResponse:
        """Export the current dataset via an adapter, as a zip of its files."""
        action = adapters.find_action(fmt)
        if action is None or action.kind != "export":
            raise HTTPException(status_code=404, detail=f"Unknown export format: {fmt}")

        state = get_state()
        from metaseed.api.client import MetaseedClient

        client = MetaseedClient.__new__(MetaseedClient)
        client._facade = state.get_or_create_facade()

        try:
            export_fn = action.resolve()
        except ModuleNotFoundError as exc:  # extra not installed
            raise HTTPException(
                status_code=400,
                detail=f"{fmt} export requires the matching metaseed extra.",
            ) from exc

        files: dict[str, str] = export_fn(client)
        if not files:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Nothing to export for {fmt}: the dataset is empty or does "
                    f"not match this format's expected structure."
                ),
            )

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        buffer.seek(0)

        stem = generate_filename(state).rsplit(".", 1)[0] or "dataset"
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stem}-{fmt}.zip"'},
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
