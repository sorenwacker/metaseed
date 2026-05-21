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
from metaseed.specs.loader import SpecLoader, SpecLoadError

from ..helpers import (
    FormContext,
    build_inline_tables,
    collect_form_values,
    extract_nested_items,
    filter_fields,
    format_validation_errors,
    get_field_data,
    get_nested_items_for_edit,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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
        except SpecLoadError:
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
    get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register core routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
        base_url: Base URL prefix for the application (e.g., "/hub").
            Should not have a trailing slash. Defaults to empty string.
    """

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Render the datasets list page."""
        from ..dataset_manager import get_manager

        state = get_state()
        manager = get_manager(state)
        datasets = manager.list_datasets()

        return templates.TemplateResponse(
            request,
            "base.html",
            {
                "datasets": [
                    {
                        "name": d.name,
                        "profile": d.profile,
                        "version": d.version,
                        "entity_count": d.entity_count,
                        "modified": d.modified,
                    }
                    for d in datasets
                ],
                "current_dataset": manager.current_dataset,
                "tree_nodes": [],
                "base_url": base_url,
            },
        )

    @app.get("/dataset/{name}/edit", response_class=HTMLResponse)
    async def edit_dataset(request: Request, name: str) -> HTMLResponse:
        """Edit a specific dataset."""
        from ..dataset_manager import get_manager

        state = get_state()
        manager = get_manager(state)

        # Load the dataset if not already loaded
        if manager.current_dataset != name:
            try:
                manager.load_dataset(name)
                # Clear editing state when switching datasets to prevent auto-redirect
                state.editing_node_id = None
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"Dataset not found: {name}") from None

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
                "current_dataset": name,
                "base_url": base_url,
            },
        )

    @app.get("/new-dataset", response_class=HTMLResponse)
    async def new_dataset(request: Request) -> HTMLResponse:
        """Show the new dataset / profile selection screen."""
        profile_factory = ProfileFactory()
        profiles_info = get_profile_display_info(profile_factory)
        return templates.TemplateResponse(
            request,
            "partials/profile_select.html",
            {"profiles": profiles_info},
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
            state.reset()  # Clear existing entities when starting fresh

            # Set the dataset name if provided
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
                "required_fields": filter_fields(fields, required=True),
                "optional_fields": filter_fields(fields, required=False, exclude_nested=True),
                "nested_fields": filter_fields(fields, nested_only=True),
                "values": auto_values,
                "auto_fields": set(auto_values.keys()),
                "current_profile": state.profile,
                "current_version": facade.version,
                "example_available": example_exists,
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
            raise HTTPException(status_code=404, detail=f"Parent node not found: {parent_id}")

        try:
            helper = getattr(facade, child_entity_type)
        except AttributeError as e:
            raise HTTPException(
                status_code=404, detail=f"Entity type not found: {child_entity_type}"
            ) from e

        state.editing_node_id = None
        state.current_nested_items = {}

        # Get fields, excluding parent reference fields (they'll be auto-filled)
        fields = get_field_data(helper, exclude_parent_ref=parent_node.entity_type)

        auto_values = {}
        auto_fields = set()

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
                "optional_fields": filter_fields(fields, required=False, exclude_nested=True),
                "nested_fields": filter_fields(fields, nested_only=True),
                "values": auto_values,
                "auto_fields": auto_fields,
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

        # Check if we're switching to a different entity
        switching_entity = state.editing_node_id != node_id

        state.editing_node_id = node_id
        state.nested_edit_stack = []

        # Always refresh nested items when switching entities or if empty
        if switching_entity or not state.current_nested_items:
            state.current_nested_items = get_nested_items_for_edit(node, helper, facade)

        fields = get_field_data(helper)
        values = {}
        if node.instance and hasattr(node.instance, "model_dump"):
            values = node.instance.model_dump(exclude_none=True)

        for field_name, items in state.current_nested_items.items():
            if items:
                values[field_name] = items

        auto_fields = set()
        if "miappe_version" in helper.all_fields:
            values["miappe_version"] = facade.version
            auto_fields.add("miappe_version")

        inline_tables = build_inline_tables(state, facade, entity_type)

        # Get child entity types that can be created under this entity
        child_entity_types = list(helper.nested_fields.values())

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
                "optional_fields": filter_fields(fields, required=False, exclude_nested=True),
                "nested_fields": filter_fields(fields, nested_only=True),
                "values": values,
                "auto_fields": auto_fields,
                "inline_tables": inline_tables,
                "child_entity_types": child_entity_types,
            },
        )


def register_entity_crud_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
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
        parent_id = form_data.get("_parent_id")

        if not entity_type:
            return error_response(request, templates, "Entity type is required")

        try:
            helper = getattr(facade, entity_type)
        except AttributeError:
            return error_response(request, templates, f"Unknown entity type: {entity_type}")

        values = collect_form_values(dict(form_data), helper)

        try:
            instance = helper.create(**values)
            node = state.add_node(entity_type, instance, parent_id=parent_id)
            state.editing_node_id = node.id

            state.current_nested_items = extract_nested_items(instance, helper)

            # Auto-save to persist changes
            from ..datasets import auto_save

            auto_save(state)

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

            # Handle reference-linked children (e.g., files added to Run)
            # These are NOT in helper.nested_fields but ARE in current_nested_items
            from ..helpers import infer_entity_type_from_field

            parent_data = instance.model_dump() if hasattr(instance, "model_dump") else {}
            parent_identifier = parent_data.get("alias") or parent_data.get("unique_id")

            import logging

            logger = logging.getLogger(__name__)
            validation_errors: list[str] = []
            failed_items: dict[str, list[dict]] = {}  # field_name -> list of failed items

            for field_name, items in state.current_nested_items.items():
                if field_name in helper.nested_fields:
                    continue  # Skip spec-defined nested fields (handled above)

                child_type = infer_entity_type_from_field(facade, entity_type, field_name)
                if not child_type:
                    continue

                child_helper = getattr(facade, child_type, None)
                if not child_helper:
                    continue

                # Find the reference field that points back to parent
                parent_ref_field = None
                for ref_field, (target_type, _) in child_helper.reference_fields.items():
                    if target_type == entity_type:
                        parent_ref_field = ref_field
                        break

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    logger.info(f"Processing {child_type} item: {list(item.keys())}")

                    # Check if this item already exists as a node (has _node_id or matches existing)
                    item_id = item.get("_node_id") or item.get("alias") or item.get("unique_id")
                    existing_node = None
                    if item_id:
                        existing_node = state.nodes_by_id.get(item_id)
                        if not existing_node:
                            # Try to find by identifier
                            for n in state.nodes_by_id.values():
                                if n.entity_type == child_type:
                                    n_data = n.instance.model_dump() if n.instance else {}
                                    if (
                                        n_data.get("alias") == item_id
                                        or n_data.get("unique_id") == item_id
                                    ):
                                        existing_node = n
                                        break

                    # Clean item data - only keep valid child entity fields
                    valid_fields = set(child_helper.all_fields)
                    cleaned = {
                        k: v
                        for k, v in item.items()
                        if not k.startswith("_") and v and k in valid_fields
                    }
                    if not cleaned:
                        continue

                    # Set parent reference field
                    if parent_ref_field and parent_identifier:
                        cleaned[parent_ref_field] = parent_identifier

                    if existing_node:
                        # Update existing node
                        try:
                            child_instance = child_helper.create(**cleaned)
                            state.update_node(existing_node.id, child_instance)
                        except ValidationError as e:
                            logger.warning(f"Validation error updating {child_type}: {e}")
                            missing = [
                                str(err["loc"][0]) for err in e.errors() if err["type"] == "missing"
                            ]
                            if missing:
                                validation_errors.append(
                                    f"{child_type}: Missing required: {', '.join(missing)}"
                                )
                            else:
                                validation_errors.append(f"{child_type}: {e.errors()[0]['msg']}")
                            # Keep the failed item
                            if field_name not in failed_items:
                                failed_items[field_name] = []
                            failed_items[field_name].append(item)
                        except Exception as e:
                            logger.warning(f"Error updating {child_type}: {e}")
                    else:
                        # Create new child node
                        try:
                            logger.info(f"Creating {child_type} with data: {cleaned}")
                            child_instance = child_helper.create(**cleaned)
                            state.add_node(child_type, child_instance, parent_id=node_id)
                        except ValidationError as e:
                            logger.warning(
                                f"Validation error creating {child_type} with {cleaned}: {e}"
                            )
                            # Get the specific error type
                            err = e.errors()[0] if e.errors() else {}
                            err_type = err.get("type", "")
                            if err_type == "missing":
                                missing = [
                                    str(err["loc"][0])
                                    for err in e.errors()
                                    if err["type"] == "missing"
                                ]
                                validation_errors.append(
                                    f"{child_type}: Missing required: {', '.join(missing)}"
                                )
                            elif err_type == "extra_forbidden":
                                extra = [
                                    str(err["loc"][0])
                                    for err in e.errors()
                                    if err["type"] == "extra_forbidden"
                                ]
                                validation_errors.append(
                                    f"{child_type}: Unknown fields: {', '.join(extra)}"
                                )
                            else:
                                validation_errors.append(f"{child_type}: {err.get('msg', str(e))}")
                            # Keep the failed item so user can fix it
                            if field_name not in failed_items:
                                failed_items[field_name] = []
                            failed_items[field_name].append(item)
                        except Exception as e:
                            logger.warning(f"Error creating {child_type}: {e}")

            # Rebuild nested items including tree children (reference-linked entities)
            updated_node = state.nodes_by_id.get(node_id)
            if updated_node:
                state.current_nested_items = get_nested_items_for_edit(updated_node, helper, facade)
            else:
                state.current_nested_items = extract_nested_items(instance, helper)

            # Add back any items that failed validation so user can fix them
            for field_name, items in failed_items.items():
                if field_name not in state.current_nested_items:
                    state.current_nested_items[field_name] = []
                for item in items:
                    # Mark as having validation error
                    item["_validation_error"] = True
                    state.current_nested_items[field_name].append(item)

            # Only auto-save if there were no validation errors
            if not validation_errors:
                from ..datasets import auto_save

                auto_save(state)

            action = form_data.get("_action", "")

            # Build appropriate message based on validation results
            if validation_errors:
                msg = f"Validation errors - please fix: {'; '.join(validation_errors)}"
                msg_type = "error"
            else:
                msg = f"Saved {entity_type}: {node.label}"
                msg_type = "success"

            if action == "back":
                return templates.TemplateResponse(
                    request,
                    "index.html",
                    {
                        "tree_nodes": state.get_tree_data(),
                        "notification": {
                            "type": msg_type,
                            "message": msg,
                        },
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

        # Auto-save to persist changes
        from ..datasets import auto_save

        auto_save(state)

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


def _build_form_context(
    helper: Any,
    entity_type: str,
    values: dict,
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
    auto_fields = set()
    if "miappe_version" in helper.all_fields:
        values["miappe_version"] = facade.version
        auto_fields.add("miappe_version")

    inline_tables = {}
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
) -> HTMLResponse:
    """Render entity form after successful create/update."""
    values = instance.model_dump(exclude_none=True) if hasattr(instance, "model_dump") else {}
    ctx = _build_form_context(helper, entity_type, values, node_id, facade, state)

    node_label = ""
    if state and node_id and node_id in state.nodes_by_id:
        node_label = state.nodes_by_id[node_id].label

    # Get child entity types that can be created under this entity
    child_entity_types = list(helper.nested_fields.values())

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
            "notification": {"type": message_type, "message": message} if message else None,
            "inline_tables": ctx.inline_tables,
            "child_entity_types": child_entity_types,
        },
    )
    response.headers["HX-Trigger"] = "entityCreated" if "Created" in message else "entityUpdated"
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
    ctx = _build_form_context(helper, entity_type, values, node_id, facade)

    return templates.TemplateResponse(
        request,
        "partials/form.html",
        {
            "entity_type": ctx.entity_type,
            "is_edit": ctx.is_edit,
            "node_id": ctx.node_id,
            "description": ctx.description,
            "ontology_term": ctx.ontology_term,
            "required_fields": ctx.get_required_fields(),
            "optional_fields": ctx.get_optional_fields(),
            "nested_fields": ctx.get_nested_fields(),
            "values": ctx.values,
            "auto_fields": ctx.auto_fields,
            "error_message": f"Validation error: {errors}",
        },
    )
