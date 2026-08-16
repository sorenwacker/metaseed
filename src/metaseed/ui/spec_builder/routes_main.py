"""Main page and initialization routes for the Spec Builder.

Handles the index page, new spec creation, cloning templates, and reset.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.schema import FieldType

from ..helpers.spec_builder_helpers import (
    clone_spec,
    create_empty_spec,
)
from .access import require_spec

if TYPE_CHECKING:
    from ..spec_persistence import SpecPersistence
    from .state import SpecBuilderState


def register_main_routes(  # noqa: C901
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
    persistence: SpecPersistence | None = None,
    base_url: str = "",
) -> None:
    """Register main page routes.

    Args:
        router: The APIRouter to add routes to.
        templates: Jinja2Templates instance.
        get_builder_state: Callable to get builder state.
        persistence: Optional persistence interface. If not provided, uses
            FilesystemSpecPersistence for backward compatibility.
        base_url: Base URL prefix for all links (no trailing slash).
    """
    if persistence is None:
        from metaseed.ui.spec_filesystem import FilesystemSpecPersistence

        persistence = FilesystemSpecPersistence()

    def _require_spec() -> SpecBuilderState:
        return require_spec(get_builder_state)

    @router.get("", response_class=HTMLResponse)
    async def spec_builder_index(request: Request) -> HTMLResponse:
        """Render the spec builder main page."""
        builder = get_builder_state()

        if builder.spec is not None:
            return templates.TemplateResponse(
                request,
                "spec_builder/base.html",
                {
                    "spec": builder.spec,
                    "editing_entity": builder.editing_entity,
                    "has_unsaved_changes": builder.has_unsaved_changes,
                    "template_source": builder.template_source,
                    "field_types": [t.value for t in FieldType],
                    "base_url": base_url,
                },
            )

        available_templates = await persistence.list_templates()
        user_specs = await persistence.list_user_specs()
        return templates.TemplateResponse(
            request,
            "spec_builder/start.html",
            {
                "templates": available_templates,
                "user_specs": user_specs,
                "base_url": base_url,
            },
        )

    @router.get("/new", response_class=HTMLResponse)
    async def new_spec(request: Request) -> HTMLResponse:
        """Start a new empty spec."""
        builder = get_builder_state()
        builder.reset()
        builder.spec = create_empty_spec()
        builder.template_source = None

        return templates.TemplateResponse(
            request,
            "spec_builder/base.html",
            {
                "spec": builder.spec,
                "editing_entity": None,
                "has_unsaved_changes": False,
                "template_source": None,
                "field_types": [t.value for t in FieldType],
                "base_url": base_url,
            },
        )

    @router.get("/clone/{profile}/{version}", response_class=HTMLResponse)
    async def clone_template(
        request: Request, profile: str, version: str
    ) -> HTMLResponse:
        """Clone an existing spec as a template."""
        from metaseed.specs.loader import SpecLoader

        builder = get_builder_state()

        try:
            spec = clone_spec(profile, version)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

        builder.reset()
        builder.spec = spec
        builder.template_source = (profile, version)

        # Load notes if they exist
        loader = SpecLoader()
        spec_path = loader.find_profile_file(version, profile)
        if spec_path:
            notes_path = spec_path.parent / "notes.md"
            if notes_path.exists():
                builder.notes = notes_path.read_text(encoding="utf-8")

        return templates.TemplateResponse(
            request,
            "spec_builder/base.html",
            {
                "spec": builder.spec,
                "editing_entity": None,
                "has_unsaved_changes": False,
                "template_source": builder.template_source,
                "field_types": [t.value for t in FieldType],
                "base_url": base_url,
            },
        )

    @router.get("/reset", response_class=HTMLResponse)
    async def reset_builder(request: Request) -> HTMLResponse:
        """Reset the spec builder to start over."""
        builder = get_builder_state()
        builder.reset()

        available_templates = await persistence.list_templates()
        user_specs = await persistence.list_user_specs()
        return templates.TemplateResponse(
            request,
            "spec_builder/start.html",
            {
                "templates": available_templates,
                "user_specs": user_specs,
                "base_url": base_url,
            },
        )

    @router.get("/select", response_class=HTMLResponse)
    async def select_spec(request: Request) -> HTMLResponse:
        """Show the spec selection page without resetting current work."""
        available_templates = await persistence.list_templates()
        user_specs = await persistence.list_user_specs()
        return templates.TemplateResponse(
            request,
            "spec_builder/start.html",
            {
                "templates": available_templates,
                "user_specs": user_specs,
                "base_url": base_url,
            },
        )

    @router.get("/profile-metadata", response_class=HTMLResponse)
    async def get_profile_metadata_form(request: Request) -> HTMLResponse:
        """Get the profile metadata form."""
        builder = _require_spec()
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/profile_metadata_form.html",
            {"spec": builder.spec},
        )

    @router.post("/profile-metadata", response_class=HTMLResponse)
    async def update_profile_metadata(
        request: Request,
    ) -> HTMLResponse:
        """Update profile metadata."""
        builder = _require_spec()
        spec = builder.spec
        assert spec is not None  # _require_spec guarantees spec is set
        form_data = await request.form()
        spec.name = cast("str", form_data.get("name", "")).strip()
        spec.version = cast("str", form_data.get("version", "")).strip()
        spec.display_name = (
            cast("str", form_data.get("display_name", "")).strip() or None
        )
        spec.description = cast("str", form_data.get("description", "")).strip()
        spec.ontology = cast("str", form_data.get("ontology", "")).strip() or None
        root_entity = cast("str", form_data.get("root_entity", "")).strip()
        if root_entity:
            # Through the builder, whose whole purpose here is to refuse a root
            # that names no entity. Assigning it directly produced a profile
            # that cannot build anything.
            # Left as it was when the entity does not exist: a root naming
            # nothing would make the profile unable to build anything, and the
            # form still shows what the draft actually holds.
            with contextlib.suppress(ValueError):
                SpecBuilder(spec).set_root_entity(root_entity)
        else:
            spec.root_entity = ""
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/profile_metadata_form.html",
            {"spec": builder.spec, "success": True},
        )

    @router.get("/notes", response_class=HTMLResponse)
    async def get_notes(request: Request) -> HTMLResponse:
        """Get the notes panel."""
        builder = get_builder_state()
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/notes_panel.html",
            {"notes": builder.notes, "spec": builder.spec},
        )

    @router.post("/notes", response_class=HTMLResponse)
    async def save_notes(request: Request) -> HTMLResponse:
        """Save notes content."""
        builder = get_builder_state()
        form_data = await request.form()
        builder.notes = cast("str", form_data.get("notes", ""))
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/notes_panel.html",
            {"notes": builder.notes, "spec": builder.spec, "saved": True},
        )
