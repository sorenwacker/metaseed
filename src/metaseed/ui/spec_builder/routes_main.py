"""Main page and initialization routes for the Spec Builder.

Handles the index page, new spec creation, cloning templates, and reset.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.schema import FieldType

from ..spec_builder_helpers import (
    clone_spec,
    create_empty_spec,
)

if TYPE_CHECKING:
    from ..spec_persistence import SpecPersistence
    from .state import SpecBuilderState


def register_main_routes(
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
    persistence: SpecPersistence | None = None,
) -> None:
    """Register main page routes.

    Args:
        router: The APIRouter to add routes to.
        templates: Jinja2Templates instance.
        get_builder_state: Callable to get builder state.
        persistence: Optional persistence interface. If not provided, uses
            FilesystemSpecPersistence for backward compatibility.
    """
    if persistence is None:
        from metaseed.ui.spec_filesystem import FilesystemSpecPersistence

        persistence = FilesystemSpecPersistence()

    def _require_spec() -> SpecBuilderState:
        """Get builder state, raising HTTPException if no spec in progress."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")
        return builder

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
                },
            )

        available_templates = await persistence.list_templates()
        user_specs = await persistence.list_user_specs()
        return templates.TemplateResponse(
            request,
            "spec_builder/start.html",
            {"templates": available_templates, "user_specs": user_specs},
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
            },
        )

    @router.get("/clone/{profile}/{version}", response_class=HTMLResponse)
    async def clone_template(request: Request, profile: str, version: str) -> HTMLResponse:
        """Clone an existing spec as a template."""
        builder = get_builder_state()

        try:
            spec = clone_spec(profile, version)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

        builder.reset()
        builder.spec = spec
        builder.template_source = (profile, version)

        return templates.TemplateResponse(
            request,
            "spec_builder/base.html",
            {
                "spec": builder.spec,
                "editing_entity": None,
                "has_unsaved_changes": False,
                "template_source": builder.template_source,
                "field_types": [t.value for t in FieldType],
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
            {"templates": available_templates, "user_specs": user_specs},
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
        form_data = await request.form()
        builder.spec.name = form_data.get("name", "").strip()
        builder.spec.version = form_data.get("version", "").strip() or "1.0"
        builder.spec.display_name = form_data.get("display_name", "").strip() or None
        builder.spec.description = form_data.get("description", "").strip()
        builder.spec.ontology = form_data.get("ontology", "").strip() or None
        builder.spec.root_entity = form_data.get("root_entity", "").strip()
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/profile_metadata_form.html",
            {"spec": builder.spec, "success": True},
        )
