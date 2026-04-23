"""Nested entity routes for editing nested items.

Provides routes for editing nested entities within forms.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..helpers import (
    build_breadcrumb,
    build_inline_tables,
    format_table_rows,
    get_field_data,
    get_items_store,
    get_parent_id_fields,
    get_reference_fields,
    get_table_columns,
    is_nested_field,
)
from ..state import NestedEditContext

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_nested_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Any,
) -> None:
    """Register nested entity routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.get("/nested/{parent_type}/{field_name}/{idx}", response_class=HTMLResponse)
    async def edit_nested_item(
        request: Request, parent_type: str, field_name: str, idx: int
    ) -> HTMLResponse:
        """Edit a nested item (e.g., a Study within an Investigation)."""
        state = get_state()
        facade = state.get_or_create_facade()
        is_resume = request.query_params.get("resume") == "true"

        try:
            parent_helper = getattr(facade, parent_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {parent_type}"
            ) from e

        if field_name not in parent_helper.nested_fields:
            raise HTTPException(status_code=404, detail=f"Field not found: {field_name}")

        nested_entity_type = parent_helper.nested_fields[field_name]
        nested_helper = getattr(facade, nested_entity_type, None)
        _, items = get_items_store(state, parent_type, field_name)

        if idx < 0 or idx >= len(items):
            raise HTTPException(status_code=404, detail=f"Row not found: {idx}")

        if is_resume and state.nested_edit_stack:
            context = state.nested_edit_stack[-1]
            item_data = items[idx]
            if hasattr(item_data, "model_dump"):
                item_data = item_data.model_dump(exclude_none=True)
            elif isinstance(item_data, dict):
                item_data = item_data.copy()
            else:
                item_data = {}
            for nf, nv in context.nested_items.items():
                item_data[nf] = nv
        else:
            item_data = items[idx]
            if hasattr(item_data, "model_dump"):
                item_data = item_data.model_dump(exclude_none=True)
            elif isinstance(item_data, dict):
                item_data = item_data.copy()
            else:
                item_data = {}

            context = NestedEditContext(
                field_name=field_name,
                row_idx=idx,
                entity_type=nested_entity_type,
                parent_entity_type=parent_type,
            )

            if nested_helper:
                for nested_field in nested_helper.nested_fields:
                    if item_data.get(nested_field):
                        nested_items = item_data[nested_field]
                        if isinstance(nested_items, list):
                            context.nested_items[nested_field] = [
                                i.model_dump() if hasattr(i, "model_dump") else i
                                for i in nested_items
                            ]

            state.nested_edit_stack.append(context)

        fields = get_field_data(nested_helper) if nested_helper else []
        values = item_data.copy() if isinstance(item_data, dict) else {}
        if state.nested_edit_stack:
            ctx = state.nested_edit_stack[-1]
            for nf, nv in ctx.nested_items.items():
                values[nf] = nv

        inline_tables = {}
        if state.nested_edit_stack:
            ctx = state.nested_edit_stack[-1]
            inline_tables = build_inline_tables(
                state, facade, nested_entity_type, items_source=ctx.nested_items
            )

        return templates.TemplateResponse(
            request,
            "partials/nested_form.html",
            {
                "entity_type": nested_entity_type,
                "parent_entity_type": parent_type,
                "field_name": field_name,
                "row_idx": idx,
                "description": nested_helper.description if nested_helper else "",
                "ontology_term": nested_helper.ontology_term if nested_helper else "",
                "required_fields": [f for f in fields if f["required"]],
                "optional_fields": [
                    f for f in fields if not f["required"] and not is_nested_field(f)
                ],
                "nested_fields": [f for f in fields if is_nested_field(f)],
                "values": values,
                "auto_fields": set(),
                "editing_node_id": state.editing_node_id,
                "breadcrumb": build_breadcrumb(state),
                "inline_tables": inline_tables,
            },
        )

    @app.post("/nested/{parent_type}/{field_name}/{idx}", response_class=HTMLResponse)
    async def save_nested_item(
        request: Request, parent_type: str, field_name: str, idx: int
    ) -> HTMLResponse:
        """Save changes to a nested item."""
        state = get_state()
        facade = state.get_or_create_facade()

        _, items = get_items_store(state, parent_type, field_name)
        if idx < 0 or idx >= len(items):
            raise HTTPException(status_code=404, detail=f"Row not found: {idx}")

        form_data = await request.form()
        go_back = form_data.get("_action") == "back"

        parent_helper = getattr(facade, parent_type, None)
        nested_entity_type = parent_helper.nested_fields.get(field_name) if parent_helper else None
        nested_helper = getattr(facade, nested_entity_type, None) if nested_entity_type else None

        item = items[idx]
        if isinstance(item, dict):
            for key, value in form_data.items():
                if not key.startswith("_"):
                    if nested_helper:
                        info = (
                            nested_helper.field_info(key) if key in nested_helper.all_fields else {}
                        )
                        if info.get("type") == "integer" and value:
                            with contextlib.suppress(ValueError):
                                value = int(value)
                        elif info.get("type") == "float" and value:
                            with contextlib.suppress(ValueError):
                                value = float(value)
                    if value:
                        item[key] = value

            if state.nested_edit_stack:
                context = state.nested_edit_stack[-1]
                for nested_field, nested_values in context.nested_items.items():
                    if nested_values:
                        item[nested_field] = nested_values

        if go_back:
            if state.nested_edit_stack:
                state.nested_edit_stack.pop()

            all_columns = get_table_columns(facade, nested_entity_type)
            reference_fields = get_reference_fields(
                profile=state.profile,
                version=facade.version,
                entity_type=nested_entity_type,
            )
            parent_id_fields = get_parent_id_fields(reference_fields, parent_type)
            display_columns = [c for c in all_columns if c not in parent_id_fields]

            return templates.TemplateResponse(
                request,
                "partials/table.html",
                {
                    "field_name": field_name,
                    "entity_type": nested_entity_type,
                    "columns": display_columns,
                    "rows": format_table_rows(items),
                    "parent_entity_type": parent_type,
                    "editing_node_id": state.editing_node_id,
                },
            )

        fields = get_field_data(nested_helper) if nested_helper else []
        values = item.copy() if isinstance(item, dict) else {}

        if state.nested_edit_stack:
            ctx = state.nested_edit_stack[-1]
            for nf, nv in ctx.nested_items.items():
                values[nf] = nv

        inline_tables = {}
        if state.nested_edit_stack:
            ctx = state.nested_edit_stack[-1]
            inline_tables = build_inline_tables(
                state, facade, nested_entity_type, items_source=ctx.nested_items
            )

        return templates.TemplateResponse(
            request,
            "partials/nested_form.html",
            {
                "entity_type": nested_entity_type,
                "parent_entity_type": parent_type,
                "field_name": field_name,
                "row_idx": idx,
                "description": nested_helper.description if nested_helper else "",
                "ontology_term": nested_helper.ontology_term if nested_helper else "",
                "required_fields": [f for f in fields if f["required"]],
                "optional_fields": [
                    f for f in fields if not f["required"] and not is_nested_field(f)
                ],
                "nested_fields": [f for f in fields if is_nested_field(f)],
                "values": values,
                "auto_fields": set(),
                "editing_node_id": state.editing_node_id,
                "breadcrumb": build_breadcrumb(state),
                "inline_tables": inline_tables,
                "success_message": "Saved",
            },
        )
