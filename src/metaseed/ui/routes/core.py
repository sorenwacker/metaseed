"""Core routes for app setup, home, and profile selection.

Provides the main page, profile switching, and form rendering routes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.requests import Request

from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader

from ..helpers import (
    build_inline_tables,
    collect_form_values,
    format_validation_errors,
    get_field_data,
    is_nested_field,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from metaseed.facade import ProfileFacade

    from ..state import AppState

UI_DIR = Path(__file__).parent.parent
EXAMPLES_DIR = UI_DIR.parent.parent.parent / "examples"


def get_profile_display_info(factory: ProfileFactory) -> list[dict]:
    """Get display information for all available profiles.

    Reads metadata from profile.yaml files.

    Args:
        factory: ProfileFactory instance.

    Returns:
        List of profile info dicts with name, display_name, description, root_entity, and versions.
    """
    profiles = []
    for name in factory.list_profiles():
        loader = SpecLoader(profile=name)
        versions = loader.list_versions(name)
        if not versions:
            continue

        latest_version = versions[-1]
        try:
            profile_spec = loader.load_profile(latest_version, name)
            profiles.append(
                {
                    "name": name,
                    "display_name": profile_spec.display_name or name.upper(),
                    "description": profile_spec.description or f"{name} metadata profile.",
                    "root_entity": profile_spec.root_entity,
                    "versions": versions,
                    "latest_version": latest_version,
                }
            )
        except Exception:
            profiles.append(
                {
                    "name": name,
                    "display_name": name.upper(),
                    "description": f"{name} metadata profile.",
                    "root_entity": "Investigation",
                    "versions": versions,
                    "latest_version": latest_version,
                }
            )
    return profiles


def register_core_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Any,
) -> None:
    """Register core routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Render the main page."""
        state = get_state()
        facade = state.get_or_create_facade()
        profile_factory = ProfileFactory()

        editing_node = None
        if state.editing_node_id:
            editing_node = state.nodes_by_id.get(state.editing_node_id)

        return templates.TemplateResponse(
            request,
            "base.html",
            {
                "profiles": profile_factory.list_profiles(),
                "current_profile": state.profile,
                "version": facade.version,
                "root_types": state.get_root_entity_types()[:3],
                "tree_nodes": state.get_tree_data(),
                "editing_node_id": state.editing_node_id,
                "editing_node_type": editing_node.entity_type if editing_node else None,
            },
        )

    @app.get("/profile/{name}")
    async def switch_profile(name: str) -> RedirectResponse:
        """Switch to a different profile."""
        state = get_state()
        profile_factory = ProfileFactory()

        if name not in profile_factory.list_profiles():
            raise HTTPException(status_code=400, detail=f"Unknown profile: {name}")

        state.profile = name
        state.facade = None
        state.reset()

        return RedirectResponse(url="/", status_code=303)

    @app.post("/reset", response_class=HTMLResponse)
    async def reset_state() -> HTMLResponse:
        """Reset all application state. Used for testing."""
        state = get_state()
        state.reset()
        return HTMLResponse(content="OK")


def register_form_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Any,
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
        if profile and profile in profile_factory.list_profiles():
            state.profile = profile
            state.version = version
            state.facade = None

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

        auto_values = {}
        if "miappe_version" in helper.all_fields:
            auto_values["miappe_version"] = facade.version

        example_exists = (EXAMPLES_DIR / state.profile / facade.version).exists()

        return templates.TemplateResponse(
            request,
            "partials/form.html",
            {
                "entity_type": entity_type,
                "is_edit": False,
                "node_id": None,
                "description": helper.description,
                "ontology_term": helper.ontology_term,
                "required_fields": [f for f in fields if f["required"]],
                "optional_fields": [
                    f for f in fields if not f["required"] and not is_nested_field(f)
                ],
                "nested_fields": [f for f in fields if is_nested_field(f)],
                "values": auto_values,
                "auto_fields": set(auto_values.keys()),
                "current_profile": state.profile,
                "current_version": facade.version,
                "example_available": example_exists,
            },
        )

    @app.get("/form/{entity_type}/{node_id}", response_class=HTMLResponse)
    async def edit_entity_form(request: Request, entity_type: str, node_id: str) -> HTMLResponse:
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

        state.editing_node_id = node_id
        state.nested_edit_stack = []

        fields = get_field_data(helper)
        values = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            values = node.instance.model_dump(exclude_none=True)

        for field_name, items in state.current_nested_items.items():
            if items:
                values[field_name] = items

        if not state.current_nested_items:
            for field_name in helper.nested_fields:
                if values.get(field_name):
                    items = values[field_name]
                    if isinstance(items, list):
                        state.current_nested_items[field_name] = [
                            item.model_dump() if hasattr(item, "model_dump") else item
                            for item in items
                        ]

        auto_fields = set()
        if "miappe_version" in helper.all_fields:
            values["miappe_version"] = facade.version
            auto_fields.add("miappe_version")

        inline_tables = build_inline_tables(state, facade, entity_type)

        return templates.TemplateResponse(
            request,
            "partials/form.html",
            {
                "entity_type": entity_type,
                "is_edit": True,
                "node_id": node_id,
                "description": helper.description,
                "ontology_term": helper.ontology_term,
                "required_fields": [f for f in fields if f["required"]],
                "optional_fields": [
                    f for f in fields if not f["required"] and not is_nested_field(f)
                ],
                "nested_fields": [f for f in fields if is_nested_field(f)],
                "values": values,
                "auto_fields": auto_fields,
                "inline_tables": inline_tables,
            },
        )


def register_entity_crud_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Any,
) -> None:
    """Register entity CRUD routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """
    from ..helpers import error_response

    @app.post("/entity", response_class=HTMLResponse)
    async def create_entity(request: Request) -> HTMLResponse:
        """Create a new entity."""
        state = get_state()
        facade = state.get_or_create_facade()

        form_data = await request.form()
        entity_type = form_data.get("_entity_type")

        if not entity_type:
            return error_response(request, templates, "Entity type is required")

        try:
            helper = getattr(facade, entity_type)
        except AttributeError:
            return error_response(request, templates, f"Unknown entity type: {entity_type}")

        values = collect_form_values(dict(form_data), helper)

        try:
            instance = helper.create(**values)
            node = state.add_node(entity_type, instance)
            state.editing_node_id = node.id

            state.current_nested_items = {}
            if hasattr(instance, "model_dump"):
                data = instance.model_dump(exclude_none=True)
                for field_name in helper.nested_fields:
                    if data.get(field_name):
                        items = data[field_name]
                        if isinstance(items, list):
                            state.current_nested_items[field_name] = [
                                item.model_dump() if hasattr(item, "model_dump") else item
                                for item in items
                            ]

            return render_entity_form(
                request,
                templates,
                facade,
                helper,
                entity_type,
                node.id,
                instance,
                f"Created {entity_type}: {node.label}",
                state,
            )

        except ValidationError as e:
            return render_form_with_errors(
                request, templates, facade, helper, entity_type, None, values, e
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
            return error_response(request, templates, f"Unknown entity type: {entity_type}")

        values = collect_form_values(dict(form_data), helper)

        for field_name, items in state.current_nested_items.items():
            if field_name in helper.nested_fields and items:
                cleaned_items = []
                for item in items:
                    if isinstance(item, dict):
                        cleaned = {k: v for k, v in item.items() if not k.startswith("_") and v}
                        if cleaned:
                            cleaned_items.append(cleaned)
                if cleaned_items:
                    values[field_name] = cleaned_items

        try:
            instance = helper.create(**values)
            state.update_node(node_id, instance)

            state.current_nested_items = {}
            if hasattr(instance, "model_dump"):
                data = instance.model_dump(exclude_none=True)
                for field_name in helper.nested_fields:
                    if data.get(field_name):
                        items = data[field_name]
                        if isinstance(items, list):
                            state.current_nested_items[field_name] = [
                                item.model_dump() if hasattr(item, "model_dump") else item
                                for item in items
                            ]

            return render_entity_form(
                request,
                templates,
                facade,
                helper,
                entity_type,
                node_id,
                instance,
                f"Saved {entity_type}: {node.label}",
                state,
            )

        except ValidationError as e:
            return render_form_with_errors(
                request, templates, facade, helper, entity_type, node_id, values, e
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

        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "notification": {
                    "type": "warning",
                    "message": f"Deleted {entity_type}: {label}",
                },
            },
        )


def render_entity_form(
    request: Request,
    templates: Jinja2Templates,
    facade: ProfileFacade,
    helper: Any,
    entity_type: str,
    node_id: str,
    instance: Any,
    success_message: str,
    state: AppState | None = None,
) -> HTMLResponse:
    """Render entity form after successful create/update."""
    fields = get_field_data(helper)
    values = instance.model_dump(exclude_none=True) if hasattr(instance, "model_dump") else {}

    auto_fields = set()
    if "miappe_version" in helper.all_fields:
        values["miappe_version"] = facade.version
        auto_fields.add("miappe_version")

    inline_tables = {}
    if state:
        inline_tables = build_inline_tables(state, facade, entity_type)

    response = templates.TemplateResponse(
        request,
        "partials/form.html",
        {
            "entity_type": entity_type,
            "is_edit": True,
            "node_id": node_id,
            "description": helper.description,
            "ontology_term": helper.ontology_term,
            "required_fields": [f for f in fields if f["required"]],
            "optional_fields": [f for f in fields if not f["required"] and not is_nested_field(f)],
            "nested_fields": [f for f in fields if is_nested_field(f)],
            "values": values,
            "auto_fields": auto_fields,
            "success_message": success_message,
            "inline_tables": inline_tables,
        },
    )
    response.headers["HX-Trigger"] = (
        "entityCreated" if "Created" in success_message else "entityUpdated"
    )
    return response


def render_form_with_errors(
    request: Request,
    templates: Jinja2Templates,
    facade: ProfileFacade,
    helper: Any,
    entity_type: str,
    node_id: str | None,
    values: dict,
    error: ValidationError,
) -> HTMLResponse:
    """Render form with validation errors."""
    errors = format_validation_errors(error)
    fields = get_field_data(helper)

    auto_fields = set()
    if "miappe_version" in helper.all_fields:
        values["miappe_version"] = facade.version
        auto_fields.add("miappe_version")

    return templates.TemplateResponse(
        request,
        "partials/form.html",
        {
            "entity_type": entity_type,
            "is_edit": node_id is not None,
            "node_id": node_id,
            "description": helper.description,
            "ontology_term": helper.ontology_term,
            "required_fields": [f for f in fields if f["required"]],
            "optional_fields": [f for f in fields if not f["required"] and not is_nested_field(f)],
            "nested_fields": [f for f in fields if is_nested_field(f)],
            "values": values,
            "auto_fields": auto_fields,
            "error_message": f"Validation error: {errors}",
        },
    )
