"""Form routes for entity creation and editing.

Provides routes for rendering new entity forms and edit forms.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from metaseed.profiles import ProfileFactory

from ..helpers import (
    build_inline_tables,
    filter_fields,
    get_field_data,
    get_nested_items_for_edit,
)
from .core import get_profile_display_info

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState

UI_DIR = Path(__file__).parent.parent


def register_form_routes(  # noqa: C901
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
) -> None:
    """Register entity form routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.get("/form/{entity_type}", response_class=HTMLResponse)
    async def new_entity_form(request: Request, entity_type: str) -> HTMLResponse:
        """Render a new entity form."""
        state = get_state()
        profile_factory = ProfileFactory()

        profile = request.query_params.get("profile")

        if not profile:
            profiles_info = get_profile_display_info(profile_factory)
            root_entities = {p["root_entity"] for p in profiles_info}
            if entity_type in root_entities:
                return templates.TemplateResponse(
                    request,
                    "partials/profile_select.html",
                    {"profiles": profiles_info},
                )

        version = request.query_params.get("version")
        dataset = request.query_params.get("dataset")

        if profile and profile in profile_factory.list_profiles():
            state.profile = profile
            state.version = version
            state.facade = None
            state.reset()

            if dataset:
                from ..datasets import set_current_dataset_name

                set_current_dataset_name(state, dataset)

        facade = state.get_or_create_facade()

        try:
            helper = getattr(facade, entity_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {entity_type}"
            ) from e

        state.editing_node_id = None
        state.current_nested_items = {}

        fields = get_field_data(helper)

        auto_values: dict[str, Any] = {}
        if "miappe_version" in helper.all_fields:
            auto_values["miappe_version"] = facade.version

        from metaseed.ui.routes.examples import example_exists as _example_exists

        example_available = _example_exists(state.profile, facade.version)

        return templates.TemplateResponse(
            request,
            "partials/form.html",
            {
                "entity_type": entity_type,
                "is_edit": False,
                "node_id": None,
                "description": helper.description,
                "ontology_term": helper.ontology_term,
                "required_fields": filter_fields(fields, required=True),
                "optional_fields": filter_fields(
                    fields, required=False, exclude_nested=True
                ),
                "nested_fields": filter_fields(fields, nested_only=True),
                "values": auto_values,
                "auto_fields": set(auto_values.keys()),
                "current_profile": state.profile,
                "current_version": facade.version,
                "example_available": example_available,
            },
        )

    @app.get("/form/child/{parent_id}/{child_entity_type}", response_class=HTMLResponse)
    async def new_child_entity_form(
        request: Request, parent_id: str, child_entity_type: str
    ) -> HTMLResponse:
        """Render a form for creating a child entity linked to a parent."""
        state = get_state()
        facade = state.get_or_create_facade()

        parent_node = state.nodes_by_id.get(parent_id)
        if not parent_node:
            raise HTTPException(
                status_code=404, detail=f"Parent node not found: {parent_id}"
            )

        try:
            helper = getattr(facade, child_entity_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {child_entity_type}"
            ) from e

        state.editing_node_id = None
        state.current_nested_items = {}

        fields = get_field_data(helper, exclude_parent_ref=parent_node.entity_type)

        auto_values: dict[str, Any] = {}
        auto_fields: set[str] = set()

        if "miappe_version" in helper.all_fields:
            auto_values["miappe_version"] = facade.version
            auto_fields.add("miappe_version")

        return templates.TemplateResponse(
            request,
            "partials/form.html",
            {
                "entity_type": child_entity_type,
                "is_edit": False,
                "node_id": None,
                "parent_id": parent_id,
                "parent_label": f"{parent_node.entity_type}: {parent_node.label}",
                "description": helper.description,
                "ontology_term": helper.ontology_term,
                "required_fields": filter_fields(fields, required=True),
                "optional_fields": filter_fields(
                    fields, required=False, exclude_nested=True
                ),
                "nested_fields": filter_fields(fields, nested_only=True),
                "values": auto_values,
                "auto_fields": auto_fields,
            },
        )

    @app.get("/form/{entity_type}/{node_id}", response_class=HTMLResponse)
    async def edit_entity_form(
        request: Request, entity_type: str, node_id: str
    ) -> HTMLResponse:
        """Render an edit form for an existing entity."""
        state = get_state()
        facade = state.get_or_create_facade()

        node = state.nodes_by_id.get(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

        try:
            helper = getattr(facade, entity_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {entity_type}"
            ) from e

        switching_entity = state.editing_node_id != node_id

        state.editing_node_id = node_id
        state.nested_edit_stack = []

        if switching_entity or not state.current_nested_items:
            state.current_nested_items = get_nested_items_for_edit(node, helper, facade)

        fields = get_field_data(helper)
        values: dict[str, Any] = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            values = node.instance.model_dump(exclude_none=True)

        for field_name, items in state.current_nested_items.items():
            if items:
                values[field_name] = items

        auto_fields: set[str] = set()
        if "miappe_version" in helper.all_fields:
            values["miappe_version"] = facade.version
            auto_fields.add("miappe_version")

        inline_tables = build_inline_tables(state, facade, entity_type)

        child_entity_types = list(helper.child_fields.values())

        return templates.TemplateResponse(
            request,
            "partials/form.html",
            {
                "entity_type": entity_type,
                "is_edit": True,
                "node_id": node_id,
                "node_label": node.label,
                "description": helper.description,
                "ontology_term": helper.ontology_term,
                "required_fields": filter_fields(fields, required=True),
                "optional_fields": filter_fields(
                    fields, required=False, exclude_nested=True
                ),
                "nested_fields": filter_fields(fields, nested_only=True),
                "values": values,
                "auto_fields": auto_fields,
                "inline_tables": inline_tables,
                "child_entity_types": child_entity_types,
            },
        )
