"""Example loading routes.

Provides routes for loading example data into the application.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

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


def example_dir(profile_name: str, version: str) -> Path | None:
    """The directory holding this profile version's example YAML, if any.

    Packaged examples live beside the package; a profile installed under the
    user data dir keeps its examples there (``examples/<profile>/<version>/``),
    beside its spec. The packaged location wins when both exist.
    """
    from metaseed.paths import user_data_base

    for base in (EXAMPLES_DIR, user_data_base() / "examples"):
        version_dir = base / profile_name / version
        if version_dir.is_dir() and any(version_dir.glob("*.yaml")):
            return version_dir
    return None


def example_exists(profile_name: str, version: str) -> bool:
    """Whether a loadable example dataset exists for this profile version.

    THE definition of "an example exists": a directory with at least one YAML
    file, exactly what the load route requires. Three modules each had their
    own copy of the path and two different answers to this question — one
    checked only that the directory existed, so a "Load Example" control could
    point at a version whose load would 404.
    """
    return example_dir(profile_name, version) is not None


def register_example_routes(
    app: FastAPI,
    get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register example loading routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        get_state: Callable returning AppState.
        base_url: URL prefix the app is mounted under (e.g. "/hub");
            redirects must carry it or they escape the mount.
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

        version_dir = example_dir(profile_name, version)
        if version_dir is None:
            raise HTTPException(
                status_code=404,
                detail=f"No example available for {profile_name} v{version}",
            )
        yaml_files = list(version_dir.glob("*.yaml"))

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

        # Keep a pristine copy: building a model to validate coerces the nested
        # dicts in ``example_data`` into model instances *in place*, and the
        # loader only descends into dicts. Loading the mutated dict would stop
        # at depth 1 and silently drop every grandchild (e.g. a Study's
        # ObservationUnits).
        document = copy.deepcopy(example_data)

        # Validate the example up front so a malformed file fails loudly rather
        # than loading a broken tree.
        try:
            Model = get_model(root_entity, version, profile=profile_name)
            Model(**example_data)
        except (ValidationError, KeyError, TypeError) as e:
            raise HTTPException(
                status_code=500, detail=f"Error creating entity from example: {e}"
            ) from e

        # The library loads the document — root and every nested entity, owned
        # children only where the profile declares containment. This route used
        # to walk it itself, which is why a consumer of the library could not
        # load an example the application could (#246).
        facade.load_nested(document, root_entity)
        roots = facade.get_roots()
        state.editing_node_id = roots[0].id if roots else None

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

        return RedirectResponse(
            url=f"{base_url}/dataset/{quote(dataset_name, safe='')}/edit",
            status_code=303,
        )
