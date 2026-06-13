"""Core routes for app setup, home, and profile selection.

Provides the main page, profile switching, and shared helper functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from metaseed.facade import ProfileFacade

    from ..state import AppState


def get_profile_display_info(factory: ProfileFactory) -> list[dict[str, Any]]:
    """Get display information for all available profiles.

    Reads metadata from profile.yaml files.

    Args:
        factory: ProfileFactory instance.

    Returns:
        List of profile info dicts with name, display_name, description,
        root_entity, and versions.
    """
    profiles: list[dict[str, Any]] = []
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
                    "display_name": profile_spec.display_name or name,
                    "description": (
                        profile_spec.description or f"{name} metadata profile."
                    ),
                    "root_entity": profile_spec.root_entity,
                    "versions": versions,
                    "latest_version": latest_version,
                }
            )
        except SpecLoadError:
            profiles.append(
                {
                    "name": name,
                    "display_name": name,
                    "description": f"{name} metadata profile.",
                    "root_entity": "Investigation",
                    "versions": versions,
                    "latest_version": latest_version,
                }
            )
    return profiles


def build_inline_tables(
    state: AppState,
    facade: ProfileFacade,
    entity_type: str,
) -> dict[str, Any]:
    """Build inline table data for child entities.

    Args:
        state: Application state.
        facade: Profile facade.
        entity_type: Current entity type.

    Returns:
        Dictionary mapping field names to inline table data.
    """
    from ..helpers.table_helpers import (
        build_inline_tables as _build_inline_tables,
    )

    return _build_inline_tables(state, facade, entity_type)


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

    def _get_dataset_manager(state: AppState) -> Any:
        """Get the dataset manager from context."""
        context = getattr(app.state, "mcp_context", None)
        if context is not None:
            return context.dataset_factory.get_manager(state)

        from ..dataset_manager import DatasetManagerFactory

        factory = DatasetManagerFactory()
        return factory.get_manager(state)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Render the datasets list page."""
        state = get_state()
        manager = _get_dataset_manager(state)
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
        state = get_state()
        manager = _get_dataset_manager(state)

        if manager.current_dataset != name:
            try:
                manager.load_dataset(name)
                from ..datasets import set_current_dataset_name

                set_current_dataset_name(state, name)
                state.editing_node_id = None
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"Dataset not found: {name}"
                ) from None

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
                "editing_node_type": (
                    editing_node.entity_type if editing_node else None
                ),
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
