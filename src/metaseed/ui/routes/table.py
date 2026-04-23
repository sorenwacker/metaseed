"""Table routes for nested entity list management.

Provides routes for viewing and editing nested entity tables.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..helpers import (
    build_breadcrumb,
    error_response,
    get_items_store,
    get_parent_id_fields,
    get_reference_fields,
    get_table_column_info,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_table_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Any,
) -> None:
    """Register table routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.get("/table/{entity_type}/{field_name}", response_class=HTMLResponse)
    async def table_view(request: Request, entity_type: str, field_name: str) -> HTMLResponse:
        """Render the nested table view for a list field."""
        state = get_state()
        facade = state.get_or_create_facade()

        try:
            helper = getattr(facade, entity_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {entity_type}"
            ) from e

        if state.editing_node_id:
            root_node = state.nodes_by_id.get(state.editing_node_id)
            if root_node and root_node.entity_type == entity_type:
                state.nested_edit_stack = []

        nested_fields = helper.nested_fields
        if field_name not in nested_fields:
            raise HTTPException(status_code=404, detail=f"Field not found: {field_name}")

        nested_entity_type = nested_fields[field_name]
        col_info = get_table_column_info(facade, nested_entity_type)
        _, items = get_items_store(state, entity_type, field_name)

        reference_fields = get_reference_fields(
            profile=state.profile,
            version=facade.version,
            entity_type=nested_entity_type,
        )

        parent_id_fields = get_parent_id_fields(reference_fields, entity_type)
        display_columns = [c for c in col_info["columns"] if c not in parent_id_fields]

        rows = []
        for i, item in enumerate(items):
            if hasattr(item, "model_dump"):
                row = item.model_dump(exclude_none=True)
            elif isinstance(item, dict):
                row = item.copy()
            else:
                row = {"value": str(item)}
            row["_idx"] = i
            rows.append(row)

        return templates.TemplateResponse(
            request,
            "partials/table.html",
            {
                "field_name": field_name,
                "entity_type": nested_entity_type,
                "columns": display_columns,
                "column_types": col_info["column_types"],
                "column_constraints": col_info["column_constraints"],
                "required_columns": col_info["required_columns"],
                "has_nested_children": col_info["has_nested_children"],
                "reference_fields": reference_fields,
                "rows": rows,
                "parent_entity_type": entity_type,
                "editing_node_id": state.editing_node_id,
                "breadcrumb": build_breadcrumb(state),
                "nested_context": state.nested_edit_stack[-1] if state.nested_edit_stack else None,
            },
        )

    @app.post("/table/{parent_entity_type}/{field_name}/row", response_class=HTMLResponse)
    async def add_table_row(
        request: Request, parent_entity_type: str, field_name: str
    ) -> HTMLResponse:
        """Add a new row to the nested table."""
        state = get_state()
        facade = state.get_or_create_facade()

        _, items = get_items_store(state, parent_entity_type, field_name)

        parent_helper = getattr(facade, parent_entity_type, None)
        entity_type = parent_helper.nested_fields.get(field_name) if parent_helper else None
        col_info = get_table_column_info(facade, entity_type)

        reference_fields = (
            get_reference_fields(
                profile=state.profile,
                version=facade.version,
                entity_type=entity_type,
            )
            if entity_type
            else {}
        )

        parent_id_fields = get_parent_id_fields(reference_fields, parent_entity_type)

        parent_identifier = ""
        if parent_id_fields and state.editing_node_id:
            node = state.nodes_by_id.get(state.editing_node_id)
            if node:
                parent_data = None
                if node.entity_type == parent_entity_type:
                    if hasattr(node.instance, "model_dump"):
                        parent_data = node.instance.model_dump(exclude_none=True)
                elif state.nested_edit_stack:
                    for ctx in reversed(state.nested_edit_stack):
                        if ctx.entity_type == parent_entity_type:
                            parent_items = state.current_nested_items.get(ctx.field_name, [])
                            if ctx.row_idx < len(parent_items):
                                parent_data = parent_items[ctx.row_idx]
                            break

                if parent_data:
                    for target_field in parent_id_fields.values():
                        if target_field in parent_data:
                            parent_identifier = str(parent_data[target_field])
                            break

        new_row = dict.fromkeys(col_info["columns"], "")
        new_row["_idx"] = len(items)

        for field_name_ref in parent_id_fields:
            if field_name_ref in new_row:
                new_row[field_name_ref] = parent_identifier

        items.append(new_row)

        hx_target = request.headers.get("hx-target", "")
        is_inline = "inline" in hx_target

        template_name = "partials/inline_table_row.html" if is_inline else "partials/table_row.html"

        display_columns = [c for c in col_info["columns"] if c not in parent_id_fields]

        return templates.TemplateResponse(
            request,
            template_name,
            {
                "row": new_row,
                "columns": display_columns,
                "column_types": col_info["column_types"],
                "column_constraints": col_info["column_constraints"],
                "reference_fields": reference_fields,
                "parent_id_fields": parent_id_fields,
                "field_name": field_name,
                "parent_entity_type": parent_entity_type,
                "entity_type": entity_type,
                "has_nested_children": col_info["has_nested_children"],
            },
        )

    @app.delete("/table/{parent_entity_type}/{field_name}/row/{idx}", response_class=HTMLResponse)
    async def delete_table_row(parent_entity_type: str, field_name: str, idx: int) -> HTMLResponse:
        """Delete a row from the nested table."""
        state = get_state()
        _, items = get_items_store(state, parent_entity_type, field_name)

        if 0 <= idx < len(items):
            del items[idx]
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    item["_idx"] = i

        return HTMLResponse(content="")

    @app.post(
        "/table/{parent_entity_type}/{field_name}/row/{idx}/cell", response_class=HTMLResponse
    )
    async def update_table_cell(
        request: Request, parent_entity_type: str, field_name: str, idx: int
    ) -> HTMLResponse:
        """Update a cell value in the nested table."""
        state = get_state()
        _, items = get_items_store(state, parent_entity_type, field_name)

        if 0 <= idx < len(items):
            form_data = await request.form()
            item = items[idx]
            if isinstance(item, dict):
                for key, value in form_data.items():
                    if not key.startswith("_"):
                        item[key] = value

        return HTMLResponse(content="")

    @app.post("/table/{parent_entity_type}/{field_name}/bulk", response_class=HTMLResponse)
    async def bulk_update_rows(
        request: Request, parent_entity_type: str, field_name: str
    ) -> HTMLResponse:
        """Bulk update multiple rows with the same value."""
        state = get_state()
        facade = state.get_or_create_facade()

        form_data = await request.form()
        field = form_data.get("bulk-edit-field", "")
        value = form_data.get("bulk-edit-value", "")
        indices_str = form_data.get("indices", "")

        if not field or not indices_str:
            return error_response(request, templates, "Field and indices are required")

        try:
            indices = [int(i.strip()) for i in indices_str.split(",") if i.strip()]
        except ValueError:
            return error_response(request, templates, "Invalid indices format")

        _, items = get_items_store(state, parent_entity_type, field_name)

        updated_count = 0
        for idx in indices:
            if 0 <= idx < len(items):
                item = items[idx]
                if isinstance(item, dict):
                    item[field] = value
                    updated_count += 1

        try:
            helper = getattr(facade, parent_entity_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {parent_entity_type}"
            ) from e

        nested_entity_type = helper.nested_fields.get(field_name)
        col_info = get_table_column_info(facade, nested_entity_type)

        reference_fields = get_reference_fields(
            profile=state.profile,
            version=facade.version,
            entity_type=nested_entity_type,
        )
        parent_id_fields = get_parent_id_fields(reference_fields, parent_entity_type)
        display_columns = [c for c in col_info["columns"] if c not in parent_id_fields]

        rows = []
        for i, item in enumerate(items):
            if hasattr(item, "model_dump"):
                row = item.model_dump(exclude_none=True)
            elif isinstance(item, dict):
                row = item.copy()
            else:
                row = {"value": str(item)}
            row["_idx"] = i
            rows.append(row)

        response = templates.TemplateResponse(
            request,
            "partials/table.html",
            {
                "field_name": field_name,
                "entity_type": nested_entity_type,
                "columns": display_columns,
                "column_types": col_info["column_types"],
                "column_constraints": col_info["column_constraints"],
                "required_columns": col_info["required_columns"],
                "has_nested_children": col_info["has_nested_children"],
                "rows": rows,
                "parent_entity_type": parent_entity_type,
                "editing_node_id": state.editing_node_id,
                "breadcrumb": build_breadcrumb(state),
                "nested_context": state.nested_edit_stack[-1] if state.nested_edit_stack else None,
                "notification": {
                    "type": "success",
                    "message": f"Updated {updated_count} rows",
                },
            },
        )
        return response

    @app.post("/table/{parent_entity_type}/{field_name}/paste", response_class=HTMLResponse)
    async def paste_cells(
        request: Request, parent_entity_type: str, field_name: str
    ) -> HTMLResponse:
        """Apply pasted cell values from clipboard."""
        state = get_state()
        form_data = await request.form()
        changes_json = form_data.get("changes", "[]")

        try:
            changes = json.loads(changes_json)
        except json.JSONDecodeError:
            return error_response(request, templates, "Invalid paste data format")

        _, items = get_items_store(state, parent_entity_type, field_name)

        updated_count = 0
        for change in changes:
            idx = change.get("idx")
            field = change.get("field")
            value = change.get("value")

            if idx is not None and field and 0 <= idx < len(items):
                item = items[idx]
                if isinstance(item, dict):
                    item[field] = value
                    updated_count += 1

        return templates.TemplateResponse(
            request,
            "components/notification.html",
            {
                "type": "success",
                "message": f"Pasted {updated_count} cells",
            },
        )
