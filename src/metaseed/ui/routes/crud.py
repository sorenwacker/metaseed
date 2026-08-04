"""Entity CRUD routes for create, update, and delete operations.

Provides routes for entity lifecycle management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.requests import Request

from ..helpers import (
    FormContext,
    build_inline_tables,
    collect_form_values,
    extract_nested_items,
    field_errors_from_validation,
    format_missing_required,
    format_validation_errors,
    missing_required_fields,
    process_reference_linked_children,
    rebuild_nested_items_with_failures,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from metaseed.facade import ProfileFacade

    from ..state import AppState


def register_entity_crud_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register entity CRUD routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
        base_url: Base URL prefix for the application (e.g., "/hub").
            Should not have a trailing slash. Defaults to empty string.
    """
    from ..helpers import error_response

    @app.post("/entity", response_class=HTMLResponse)
    async def create_entity(request: Request) -> HTMLResponse:
        """Create a new entity."""
        state = get_state()
        facade = state.get_or_create_facade()

        form_data = await request.form()
        entity_type_raw = form_data.get("_entity_type")
        parent_id_raw = form_data.get("_parent_id")

        if not entity_type_raw or not isinstance(entity_type_raw, str):
            return error_response(request, templates, "Entity type is required")

        entity_type: str = entity_type_raw
        parent_id: str | None = (
            parent_id_raw if isinstance(parent_id_raw, str) else None
        )

        try:
            helper = getattr(facade, entity_type)
        except AttributeError:
            return error_response(
                request, templates, f"Unknown entity type: {entity_type}"
            )

        values = collect_form_values(dict(form_data), helper)

        # Progressive editing: creating an entity must never be blocked by
        # validation. When the values are valid, create normally; otherwise save
        # an incomplete draft (skip_validation) and surface the issues as a
        # non-blocking warning, so a user can create a root entity and fill its
        # required children afterwards.
        try:
            instance = helper.create(**values)
            # Building no longer fails on a missing required field, so the
            # guidance has to be looked for rather than caught.
            missing = missing_required_fields(instance, values)
            warning = format_missing_required(missing) or None
            field_errors: dict[str, str] = dict.fromkeys(
                missing, "This field is required"
            )
        except ValidationError as e:
            instance = helper.create(skip_validation=True, **values)
            warning = format_validation_errors(e)
            field_errors = field_errors_from_validation(e)

        node = state.add_node(
            entity_type,
            instance,
            parent_id=parent_id,
            skip_validation=warning is not None,
        )
        state.editing_node_id = node.id
        state.current_nested_items = extract_nested_items(instance, helper)

        from ..datasets import auto_save

        auto_save(state)

        if warning:
            message = (
                f"Saved draft {entity_type}: {node.label} (incomplete — {warning})"
            )
            message_type = "warning"
        else:
            message = f"Created {entity_type}: {node.label}"
            message_type = "success"

        return render_entity_form(
            request,
            templates,
            facade,
            helper,
            str(entity_type),
            node.id,
            instance,
            message,
            state,
            message_type=message_type,
            created=True,
            field_errors=field_errors,
        )

    @app.put("/entity/{node_id}", response_class=HTMLResponse)
    async def update_entity(request: Request, node_id: str) -> HTMLResponse:
        """Update an existing entity."""
        state = get_state()
        facade = state.get_or_create_facade()

        node = state.nodes_by_id.get(node_id)
        if not node:
            return error_response(request, templates, f"Node not found: {node_id}")

        form_data = await request.form()
        entity_type = node.entity_type

        try:
            helper = getattr(facade, entity_type)
        except AttributeError:
            return error_response(
                request, templates, f"Unknown entity type: {entity_type}"
            )

        values = collect_form_values(dict(form_data), helper)

        # Nested entity items are materialized as standalone child nodes by
        # process_reference_linked_children below, so they are intentionally not
        # embedded into the parent here -- embedding as well would list each item
        # twice in the edit view (once from the parent, once from the child node).

        # Saving must never be blocked by validation. Persist the parent as a
        # draft (skip_validation) when it is incomplete, collecting the issues as
        # a non-blocking warning alongside any child reference-linking failures.
        try:
            instance = helper.create(**values)
            # As on create: a missing required field no longer raises, so the
            # warning has to be looked for rather than caught.
            missing = missing_required_fields(instance, values)
            parent_warning = format_missing_required(missing) or None
            field_errors: dict[str, str] = dict.fromkeys(
                missing, "This field is required"
            )
        except ValidationError as e:
            instance = helper.create(skip_validation=True, **values)
            parent_warning = format_validation_errors(e)
            field_errors = field_errors_from_validation(e)

        state.update_node(node_id, instance, skip_validation=parent_warning is not None)

        parent_data = instance.model_dump() if hasattr(instance, "model_dump") else {}
        parent_identifier = parent_data.get("alias") or parent_data.get("unique_id")

        validation_result = process_reference_linked_children(
            state=state,
            facade=facade,
            node_id=node_id,
            entity_type=entity_type,
            parent_identifier=parent_identifier,
        )

        rebuild_nested_items_with_failures(
            state=state,
            node_id=node_id,
            helper=helper,
            facade=facade,
            failed_items=validation_result.failed_items,
        )

        # Always persist — a draft save is not rejected for incompleteness.
        from ..datasets import auto_save

        auto_save(state)

        action = form_data.get("_action", "")

        problems = list(validation_result.errors)
        if parent_warning:
            problems.append(parent_warning)
        if problems:
            msg = f"Saved draft {entity_type}: {node.label} (incomplete — {'; '.join(problems)})"
            msg_type = "warning"
        else:
            msg = f"Saved {entity_type}: {node.label}"
            msg_type = "success"

        if action == "back":
            return templates.TemplateResponse(
                request,
                "index.html",
                {
                    "tree_nodes": state.get_tree_data(),
                    "root_types": state.get_root_entity_types()[:3],
                    "current_profile": state.profile,
                    "version": facade.version,
                    "notification": {"type": msg_type, "message": msg},
                    "base_url": base_url,
                },
            )

        return render_entity_form(
            request,
            templates,
            facade,
            helper,
            entity_type,
            node_id,
            instance,
            msg,
            state,
            message_type=msg_type,
            created=False,
            field_errors=field_errors,
        )

    @app.delete("/entity/{node_id}", response_class=HTMLResponse)
    async def delete_entity(request: Request, node_id: str) -> HTMLResponse:
        """Delete an entity."""
        state = get_state()

        node = state.nodes_by_id.get(node_id)
        if not node:
            return error_response(request, templates, f"Node not found: {node_id}")

        entity_type = node.entity_type
        label = node.label

        state.delete_node(node_id)

        from ..datasets import auto_save

        auto_save(state)

        facade = state.get_or_create_facade()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "tree_nodes": state.get_tree_data(),
                "root_types": state.get_root_entity_types()[:3],
                "current_profile": state.profile,
                "version": facade.version,
                "notification": {
                    "type": "warning",
                    "message": f"Deleted {entity_type}: {label}",
                },
                "base_url": base_url,
            },
        )


def _build_form_context(
    helper: Any,
    entity_type: str,
    values: dict[str, Any],
    node_id: str | None,
    facade: ProfileFacade,
    state: AppState | None = None,
) -> FormContext:
    """Build a FormContext with auto-populated fields.

    Args:
        helper: Entity helper from facade.
        entity_type: Entity type name.
        values: Form values dict.
        node_id: Node ID if editing, None if creating.
        facade: Profile facade.
        state: App state for inline tables.

    Returns:
        Populated FormContext instance.
    """
    auto_fields: set[str] = set()
    if "miappe_version" in helper.all_fields:
        values["miappe_version"] = facade.version
        auto_fields.add("miappe_version")

    inline_tables: dict[str, Any] = {}
    if state:
        inline_tables = build_inline_tables(state, facade, entity_type)

    return FormContext(
        entity_type=entity_type,
        helper=helper,
        values=values,
        node_id=node_id,
        auto_fields=auto_fields,
        inline_tables=inline_tables,
    )


def render_entity_form(
    request: Request,
    templates: Jinja2Templates,
    facade: ProfileFacade,
    helper: Any,
    entity_type: str,
    node_id: str,
    instance: Any,
    message: str,
    state: AppState | None = None,
    message_type: str = "success",
    created: bool = False,
    field_errors: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render entity form after successful create/update."""
    values = (
        instance.model_dump(exclude_none=True)
        if hasattr(instance, "model_dump")
        else {}
    )
    ctx = _build_form_context(helper, entity_type, values, node_id, facade, state)

    node_label = ""
    if state and node_id and node_id in state.nodes_by_id:
        node_label = state.nodes_by_id[node_id].label

    child_entity_types = list(helper.child_fields.values())

    from .import_export import export_options_for_profile

    export_options = (
        export_options_for_profile(state.profile) if state is not None else []
    )

    response = templates.TemplateResponse(
        request,
        "partials/form.html",
        {
            "entity_type": ctx.entity_type,
            "is_edit": ctx.is_edit,
            "node_id": ctx.node_id,
            "node_label": node_label,
            "description": ctx.description,
            "ontology_term": ctx.ontology_term,
            "required_fields": ctx.get_required_fields(),
            "optional_fields": ctx.get_optional_fields(),
            "nested_fields": ctx.get_nested_fields(),
            "values": ctx.values,
            "auto_fields": ctx.auto_fields,
            "notification": (
                {"type": message_type, "message": message} if message else None
            ),
            "inline_tables": ctx.inline_tables,
            "child_entity_types": child_entity_types,
            "field_errors": field_errors or {},
            "export_options": export_options,
        },
    )
    response.headers["HX-Trigger"] = "entityCreated" if created else "entityUpdated"
    return response
