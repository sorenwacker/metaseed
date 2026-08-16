"""Entity management routes for the Spec Builder.

Handles CRUD operations for entities within a specification.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.seek.roles import SEEK_ROLES
from metaseed.specs.builder import SpecBuilder
from metaseed.ui.spec_builder.access import (
    entity_editor_response,
    require_entity,
    require_spec,
)

if TYPE_CHECKING:
    from .state import SpecBuilderState


def register_entity_routes(  # noqa: C901
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
    _base_url: str = "",
) -> None:
    """Register entity management routes.

    Args:
        router: The APIRouter to add routes to.
        templates: Jinja2Templates instance.
        get_builder_state: Callable to get builder state.
        _base_url: Base URL prefix for all links (no trailing slash).
            Currently unused.
    """

    def _require_spec() -> SpecBuilderState:
        return require_spec(get_builder_state)

    _require_entity = require_entity

    def _entity_list_response(
        request: Request, builder: SpecBuilderState, error: str | None = None
    ) -> HTMLResponse:
        """Helper to return entity list template response."""
        assert builder.spec is not None  # guaranteed by _require_spec
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entities_list.html",
            {
                "entities": builder.spec.entities,
                "editing_entity": builder.editing_entity,
                "root_entity": builder.spec.root_entity,
                "error": error,
            },
        )

    def _entity_editor_response(
        request: Request,
        builder: SpecBuilderState,
        entity_name: str,
        error: str | None = None,
        success: bool = False,
    ) -> HTMLResponse:
        return entity_editor_response(
            templates, request, builder, entity_name, error, success
        )

    @router.get("/entities", response_class=HTMLResponse)
    async def get_entities_list(request: Request) -> HTMLResponse:
        """Get the entities list panel."""
        builder = _require_spec()
        return _entity_list_response(request, builder)

    @router.post("/entity", response_class=HTMLResponse)
    async def add_entity(
        request: Request,
        name: str = Form(...),
    ) -> HTMLResponse:
        """Add a new entity."""
        builder = _require_spec()
        assert builder.spec is not None  # guaranteed by _require_spec
        name = name.strip()
        try:
            SpecBuilder.from_spec(builder.spec).add_entity(name)
        except ValueError as error:
            return _entity_list_response(request, builder, str(error))

        builder.editing_entity = name
        builder.editing_field_idx = None
        builder.mark_changed()

        # If first entity and no root set, make it the root
        if not builder.spec.root_entity:
            builder.spec.root_entity = name

        return _entity_editor_response(request, builder, name)

    @router.get("/entity/{name}", response_class=HTMLResponse)
    async def get_entity(request: Request, name: str) -> HTMLResponse:
        """Get entity editor form."""
        builder = _require_spec()
        _require_entity(builder, name)
        builder.editing_entity = name
        builder.editing_field_idx = None

        return _entity_editor_response(request, builder, name)

    @router.put("/entity/{name}", response_class=HTMLResponse)
    async def update_entity(
        request: Request,
        name: str,
        new_name: str = Form(None, alias="name"),
        description: str = Form(""),
        ontology_term: str = Form(""),
        seek_role: str | None = Form(None),
    ) -> HTMLResponse:
        """Update entity metadata, including rename."""
        from metaseed.specs.schema import SeekEntityConfig

        builder = _require_spec()
        assert builder.spec is not None  # guaranteed by _require_spec
        entity = _require_entity(builder, name)
        entity.description = description.strip()
        entity.ontology_term = ontology_term.strip() or None
        # Only touch entity.seek when the form actually carried the field, so a
        # post that omits it (older form / API caller) preserves a saved role.
        # An empty or unrecognized value clears it (dropdown "— none —").
        if seek_role is not None:
            role = seek_role.strip()
            entity.seek = SeekEntityConfig(role=role) if role in SEEK_ROLES else None

        # Handle rename
        final_name = name
        if new_name and new_name.strip() != name:
            new_name = new_name.strip()
            try:
                SpecBuilder.from_spec(builder.spec).rename_entity(name, new_name)
            except ValueError as error:
                return _entity_editor_response(request, builder, name, error=str(error))

            # Update editing state (UI concern, not handled by the engine)
            if builder.editing_entity == name:
                builder.editing_entity = new_name

            final_name = new_name

        builder.mark_changed()

        return _entity_editor_response(request, builder, final_name, success=True)

    @router.delete("/entity/{name}", response_class=HTMLResponse)
    async def delete_entity(request: Request, name: str) -> HTMLResponse:
        """Delete an entity."""
        builder = _require_spec()
        assert builder.spec is not None  # guaranteed by _require_spec
        _require_entity(builder, name)
        SpecBuilder.from_spec(builder.spec).delete_entity(name)

        # Clear editing state if we were editing this entity (UI concern)
        if builder.editing_entity == name:
            builder.editing_entity = None
            builder.editing_field_idx = None

        builder.mark_changed()

        return _entity_list_response(request, builder)
