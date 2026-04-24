"""Example loading routes.

Provides routes for loading example data into the application.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from metaseed.models import get_model
from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState

UI_DIR = Path(__file__).parent.parent
EXAMPLES_DIR = UI_DIR.parent.parent.parent / "examples"


def register_example_routes(
    app: FastAPI,
    get_state: Callable[[], AppState],
) -> None:
    """Register example loading routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        get_state: Callable returning AppState.
    """

    @app.get("/load-example/{profile_name}/{version}")
    async def load_example(profile_name: str, version: str) -> RedirectResponse:
        """Load example data for a profile version."""
        state = get_state()
        profile_factory = ProfileFactory()

        if profile_name not in profile_factory.list_profiles():
            raise HTTPException(status_code=400, detail=f"Unknown profile: {profile_name}")

        version_dir = EXAMPLES_DIR / profile_name / version

        if not version_dir.exists():
            raise HTTPException(
                status_code=404, detail=f"No example available for {profile_name} v{version}"
            )

        yaml_files = list(version_dir.glob("*.yaml"))
        if not yaml_files:
            raise HTTPException(status_code=404, detail=f"No example file found in {version_dir}")

        example_file = yaml_files[0]

        try:
            example_data = yaml.safe_load(example_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise HTTPException(status_code=500, detail=f"Error loading example: {e}") from e

        state.reset()
        state.profile = profile_name
        state.version = version
        state.facade = None
        facade = state.get_or_create_facade()

        loader = SpecLoader(profile=profile_name)
        spec = loader.load_profile(version, profile_name)
        root_entity = spec.root_entity or "Investigation"

        try:
            Model = get_model(root_entity, version, profile=profile_name)
            instance = Model(**example_data)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error creating entity from example: {e}"
            ) from e

        node = state.add_node(root_entity, instance)
        state.editing_node_id = node.id

        helper = getattr(facade, root_entity)
        for field_name in helper.nested_fields:
            if example_data.get(field_name):
                items = example_data[field_name]
                if isinstance(items, list):
                    state.current_nested_items[field_name] = list(items)
                elif isinstance(items, dict):
                    state.current_nested_items[field_name] = [items]

        return RedirectResponse(url="/", status_code=303)
