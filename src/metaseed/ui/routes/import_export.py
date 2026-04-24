"""Import/export routes for data transfer.

Provides routes for exporting to Excel and importing ISA data.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.requests import Request

from ..helpers import error_response
from ..services.export import export_to_bytes, generate_filename

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

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
    """Register import routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.post("/import", response_class=HTMLResponse)
    async def import_isa(
        request: Request,
        file: UploadFile = File(...),
    ) -> HTMLResponse:
        """Import ISA-JSON file and create entities."""
        from metaseed.importers.isa import ISAImporter

        state = get_state()
        facade = state.get_or_create_facade()

        filename = file.filename or ""
        content = await file.read()

        try:
            importer = ISAImporter()

            if filename.endswith(".json"):
                with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                result = importer.import_json(tmp_path)
                Path(tmp_path).unlink()
            else:
                return error_response(
                    request,
                    templates,
                    "Unsupported file type. Please upload an ISA-JSON file (.json).",
                )

            if result.investigation and "Investigation" in facade.entities:
                helper = facade.Investigation
                inv_data = result.investigation.copy()

                if state.profile == "miappe" and "miappe_version" in helper.all_fields:
                    inv_data["miappe_version"] = facade.version

                if result.studies and "studies" in helper.nested_fields:
                    inv_data["studies"] = result.studies

                if result.persons:
                    for field_name in ["persons", "contacts", "people"]:
                        if field_name in helper.nested_fields:
                            inv_data[field_name] = result.persons
                            break

                try:
                    instance = helper.create(**inv_data)
                    node = state.add_node("Investigation", instance)
                    state.editing_node_id = node.id
                    state.current_nested_items = {}

                    if result.studies:
                        state.current_nested_items["studies"] = result.studies
                    if result.persons:
                        for field_name in ["persons", "contacts", "people"]:
                            if field_name in helper.nested_fields:
                                state.current_nested_items[field_name] = result.persons
                                break

                except ValidationError:
                    pass

            response = templates.TemplateResponse(
                request,
                "components/notification.html",
                {
                    "type": "success",
                    "message": result.summary,
                },
            )
            response.headers["HX-Trigger"] = "refreshPage"
            return response

        except Exception as e:
            return error_response(request, templates, f"Import failed: {e!s}")
