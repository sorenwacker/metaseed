"""Nested entity routes for editing nested items.

Provides routes for editing nested entities within forms.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from metaseed.ui.services.heading_note import field_notes

from ..helpers import (
    build_breadcrumb,
    build_inline_tables,
    form_field_groups,
    format_table_rows,
    get_field_data,
    get_items_store,
    get_parent_id_fields,
    get_reference_fields,
    get_table_columns,
    store_children_and_save,
)
from ..state import NestedEditContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from metaseed.facade import ProfileFacade

    from ..state import AppState


def _save_through_the_open_record(
    state: AppState, facade: ProfileFacade, request: Request
) -> str | None:
    """Fold the nested edits into the open record's rows, then store and write.

    A row being edited at depth k lives in the rows of the form at depth k-1,
    and only the open record's rows (``current_nested_items``) are stored as
    records, so each level's edits are copied down into the row it belongs to
    first.

    Returns:
        The reason the dataset was not written, or None when it was.
    """
    if not state.editing_node_id or state.editing_node_id not in state.nodes_by_id:
        return "no record is open"
    stack = state.nested_edit_stack
    for depth in range(len(stack) - 1, -1, -1):
        ctx = stack[depth]
        store = stack[depth - 1].nested_items if depth else state.current_nested_items
        rows = store.get(ctx.field_name, [])
        if ctx.row_idx < len(rows) and isinstance(rows[ctx.row_idx], dict):
            for nested_field, nested_values in ctx.nested_items.items():
                if nested_values:
                    rows[ctx.row_idx][nested_field] = nested_values
    _, save_error = store_children_and_save(
        state,
        facade,
        state.editing_node_id,
        getattr(request.app.state, "dataset_factory", None),
    )
    return save_error


def _coerce_form_value(value: str, field_type: str | None) -> object | None:
    """Coerce a raw form field value to its typed value.

    Args:
        value: Raw string value from the submitted form.
        field_type: The nested field's declared type, if known.

    Returns:
        The typed value, or None when the field was left blank and should be
        dropped. Numeric zero is preserved, unlike a plain truthiness check.
    """
    if value == "":
        return None
    if field_type == "integer":
        with contextlib.suppress(ValueError):
            return int(value)
    elif field_type == "float":
        with contextlib.suppress(ValueError):
            return float(value)
    return value


def register_nested_routes(  # noqa: C901
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
) -> None:
    """Register nested entity routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.get("/nested/{parent_type}/{field_name}/{idx}", response_class=HTMLResponse)
    async def edit_nested_item(  # noqa: C901
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
            raise HTTPException(
                status_code=404, detail=f"Field not found: {field_name}"
            )

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
                state, facade, nested_entity_type or "", items_source=ctx.nested_items
            )

        return templates.TemplateResponse(
            request,
            "partials/nested_form.html",
            {
                "field_notes": field_notes(nested_helper, facade.profile_spec)
                if nested_helper
                else {},
                "entity_type": nested_entity_type,
                "parent_entity_type": parent_type,
                "field_name": field_name,
                "row_idx": idx,
                "description": nested_helper.description if nested_helper else "",
                "ontology_term": nested_helper.ontology_term if nested_helper else "",
                **form_field_groups(fields),
                "values": values,
                "auto_fields": set(),
                "editing_node_id": state.editing_node_id,
                "breadcrumb": build_breadcrumb(state),
                "inline_tables": inline_tables,
            },
        )

    @app.post("/nested/{parent_type}/{field_name}/{idx}", response_class=HTMLResponse)
    async def save_nested_item(  # noqa: C901
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
        nested_entity_type = (
            parent_helper.nested_fields.get(field_name) if parent_helper else None
        )
        nested_helper = (
            getattr(facade, nested_entity_type, None) if nested_entity_type else None
        )

        item = items[idx]
        if isinstance(item, dict):
            for key, value in form_data.items():
                if key.startswith("_") or not isinstance(value, str):
                    continue
                field_type = None
                if nested_helper and key in nested_helper.all_fields:
                    field_type = nested_helper.field_info(key).get("type")
                coerced = _coerce_form_value(value, field_type)
                if coerced is not None:
                    item[key] = coerced
                elif value == "":
                    # A blank submission clears the field, matching the table-cell
                    # editors (which write the raw value); otherwise a nested field
                    # could never be emptied once set.
                    item[key] = ""

            if state.nested_edit_stack:
                context = state.nested_edit_stack[-1]
                for nested_field, nested_values in context.nested_items.items():
                    if nested_values:
                        item[nested_field] = nested_values

        # Saving the row's form writes the dataset, as the open record's Save
        # does; answering "Saved" for a change held only in the session lost
        # the record when the session ended (#356).
        save_error = _save_through_the_open_record(state, facade, request)

        if go_back:
            if state.nested_edit_stack:
                state.nested_edit_stack.pop()

            all_columns = get_table_columns(facade, nested_entity_type or "")
            reference_fields = get_reference_fields(
                profile=state.profile,
                version=facade.version,
                entity_type=nested_entity_type or "",
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
                state, facade, nested_entity_type or "", items_source=ctx.nested_items
            )

        return templates.TemplateResponse(
            request,
            "partials/nested_form.html",
            {
                "field_notes": field_notes(nested_helper, facade.profile_spec)
                if nested_helper
                else {},
                "entity_type": nested_entity_type,
                "parent_entity_type": parent_type,
                "field_name": field_name,
                "row_idx": idx,
                "description": nested_helper.description if nested_helper else "",
                "ontology_term": nested_helper.ontology_term if nested_helper else "",
                **form_field_groups(fields),
                "values": values,
                "auto_fields": set(),
                "editing_node_id": state.editing_node_id,
                "breadcrumb": build_breadcrumb(state),
                "inline_tables": inline_tables,
                "success_message": None if save_error else "Saved",
                "error_message": f"Not saved: {save_error}" if save_error else None,
            },
        )
