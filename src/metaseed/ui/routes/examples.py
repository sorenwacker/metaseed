"""Example loading routes.

Provides routes for loading example data into the application.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from metaseed.models import get_model
from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState

UI_DIR = Path(__file__).parent.parent
EXAMPLES_DIR = UI_DIR.parent / "examples"


def _materialize_children(
    state: AppState,
    facade: object,
    parent_node_id: str,
    parent_type: str,
    parent_data: dict[str, object],
) -> None:
    """Recursively add an example's nested entities as tree nodes.

    Walks each nested relationship of ``parent_type`` and creates a child node
    for every embedded object, so a loaded example lists its whole entity tree
    rather than just the root. Plain string references (not embedded objects) are
    skipped — they are links, not owned children.
    """
    helper = getattr(facade, parent_type, None)
    if helper is None:
        return
    for field_name, child_type in helper.nested_fields.items():
        items = parent_data.get(field_name)
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue
        child_helper = getattr(facade, child_type, None)
        if child_helper is None:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue  # a string reference, not an embedded child
            child_instance = child_helper.create(skip_validation=True, **item)
            child_node = state.add_node(
                child_type, child_instance, parent_id=parent_node_id
            )
            _materialize_children(state, facade, child_node.id, child_type, item)


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
            raise HTTPException(
                status_code=400, detail=f"Unknown profile: {profile_name}"
            )

        version_dir = EXAMPLES_DIR / profile_name / version

        if not version_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No example available for {profile_name} v{version}",
            )

        yaml_files = list(version_dir.glob("*.yaml"))
        if not yaml_files:
            raise HTTPException(
                status_code=404, detail=f"No example file found in {version_dir}"
            )

        example_file = yaml_files[0]

        try:
            example_data = yaml.safe_load(example_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=500, detail=f"Error loading example: {e}"
            ) from e

        state.reset()
        state.profile = profile_name
        state.version = version
        state.facade = None
        facade = state.get_or_create_facade()

        loader = SpecLoader(profile=profile_name)
        spec = loader.load_profile(version, profile_name)
        root_entity = spec.root_entity or "Investigation"

        # Validate the example up front so a malformed file fails loudly rather
        # than loading a broken tree.
        try:
            Model = get_model(root_entity, version, profile=profile_name)
            Model(**example_data)
        except (ValidationError, KeyError, TypeError) as e:
            raise HTTPException(
                status_code=500, detail=f"Error creating entity from example: {e}"
            ) from e

        helper = getattr(facade, root_entity)
        root_instance = helper.create(skip_validation=True, **example_data)
        node = state.add_node(root_entity, root_instance)
        state.editing_node_id = node.id

        # Materialize every nested entity as its own tree node (recursively), so
        # the whole dataset is listed, not just the root. Children carried inline
        # in the parent's scalar fields would otherwise be invisible in the tree.
        _materialize_children(state, facade, node.id, root_entity, example_data)

        # Persist the loaded example as a named dataset and open its edit view.
        # The datasets overview at "/" does not render in-memory state, so a bare
        # redirect there would leave the freshly loaded example invisible.
        from ..datasets import save_dataset, set_current_dataset_name

        # Dataset names allow only alphanumerics, hyphens and underscores, so the
        # version's dots must be normalised (e.g. "1.0" -> "1_0").
        safe_version = version.replace(".", "_")
        dataset_name = f"{profile_name}-{safe_version}-example"
        save_dataset(state, dataset_name)
        set_current_dataset_name(state, dataset_name)

        return RedirectResponse(url=f"/dataset/{dataset_name}/edit", status_code=303)
