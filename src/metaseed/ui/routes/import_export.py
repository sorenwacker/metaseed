"""Import/export routes for data transfer.

Provides routes for exporting to Excel and importing ISA data.
"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.requests import Request

from ..helpers import error_response

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_export_routes(
    app: FastAPI,
    templates: Jinja2Templates,  # noqa: ARG001
    get_state: Any,
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
        from datetime import datetime

        from openpyxl import Workbook

        state = get_state()
        facade = state.get_or_create_facade()

        wb = Workbook()
        wb.remove(wb.active)

        entities_by_type: dict[str, list[dict]] = {}

        def extract_nested_entities(data: dict, entity_type: str) -> None:
            helper = getattr(facade, entity_type, None)
            if not helper:
                return

            for field_name, nested_type in helper.nested_fields.items():
                if data.get(field_name):
                    nested_items = data[field_name]
                    if isinstance(nested_items, list):
                        for item in nested_items:
                            if hasattr(item, "model_dump"):
                                item_data = item.model_dump(exclude_none=True)
                            elif isinstance(item, dict):
                                item_data = item.copy()
                            else:
                                continue

                            if nested_type not in entities_by_type:
                                entities_by_type[nested_type] = []
                            entities_by_type[nested_type].append(item_data)
                            extract_nested_entities(item_data, nested_type)

        for node in state.nodes_by_id.values():
            entity_type = node.entity_type
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []

            if hasattr(node.instance, "model_dump"):
                data = node.instance.model_dump(exclude_none=True)
            else:
                data = {}

            entities_by_type[entity_type].append(data)
            extract_nested_entities(data, entity_type)

        for entity_type in facade.entities:
            helper = getattr(facade, entity_type, None)
            if not helper:
                continue

            ws = wb.create_sheet(entity_type)
            nested_fields = set(helper.nested_fields.keys())
            columns = helper.all_fields

            ws.append(columns)

            entities = entities_by_type.get(entity_type, [])
            for entity_data in entities:
                row = []
                for col in columns:
                    value = entity_data.get(col, "")
                    if col in nested_fields:
                        if isinstance(value, list):
                            value = len(value)
                        elif value:
                            value = 1
                        else:
                            value = 0
                    elif isinstance(value, list):
                        if value and not isinstance(value[0], dict):
                            value = ", ".join(str(v) for v in value)
                        else:
                            value = len(value)
                    elif isinstance(value, dict):
                        value = "[object]"
                    elif not isinstance(value, str | int | float | bool | type(None)):
                        value = str(value)
                    row.append(value)
                ws.append(row)

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        date_str = datetime.now().strftime("%y%m%d")
        version_str = facade.version.replace(".", "-")

        entity_id = "export"
        root_nodes = [n for n in state.nodes_by_id.values() if n.parent_id is None]
        if root_nodes:
            root_node = root_nodes[0]
            if hasattr(root_node.instance, "model_dump"):
                root_data = root_node.instance.model_dump()
                if root_data.get("unique_id"):
                    entity_id = str(root_data["unique_id"]).replace("/", "-").replace(":", "-")[:30]

        filename = f"{date_str}-{state.profile}-{version_str}-{entity_id}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def register_import_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Any,
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
