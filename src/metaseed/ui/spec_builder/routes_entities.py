"""Entity management routes for the Spec Builder.

Handles CRUD operations for entities within a specification.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.schema import EntityDefSpec, FieldType

from ..spec_builder_helpers import validate_entity_name

if TYPE_CHECKING:
    from .state import SpecBuilderState


def register_entity_routes(
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
        base_url: Base URL prefix for all links (no trailing slash).
    """

    def _require_spec() -> SpecBuilderState:
        """Get builder state, raising HTTPException if no spec in progress."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")
        return builder

    def _require_entity(builder: SpecBuilderState, name: str) -> EntityDefSpec:
        """Get entity by name, raising HTTPException if not found."""
        if name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
        return builder.spec.entities[name]

    def _entity_list_response(
        request: Request, builder: SpecBuilderState, error: str | None = None
    ) -> HTMLResponse:
        """Helper to return entity list template response."""
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
        """Helper to return entity editor template response."""
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": entity_name,
                "entity": builder.spec.entities[entity_name],
                "editing_field_idx": builder.editing_field_idx,
                "field_types": [t.value for t in FieldType],
                "error": error,
                "success": success,
            },
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
        name = name.strip()
        error = validate_entity_name(name)
        if error:
            return _entity_list_response(request, builder, error)

        if name in builder.spec.entities:
            return _entity_list_response(request, builder, f"Entity '{name}' already exists")

        builder.spec.entities[name] = EntityDefSpec(
            ontology_term=None,
            description="",
            fields=[],
        )
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
    ) -> HTMLResponse:
        """Update entity metadata, including rename."""
        builder = _require_spec()
        entity = _require_entity(builder, name)
        entity.description = description.strip()
        entity.ontology_term = ontology_term.strip() or None

        # Handle rename
        final_name = name
        if new_name and new_name.strip() != name:
            new_name = new_name.strip()

            error = validate_entity_name(new_name)
            if error:
                return _entity_editor_response(request, builder, name, error=error)

            if new_name in builder.spec.entities:
                return _entity_editor_response(
                    request, builder, name, error=f"Entity '{new_name}' already exists"
                )

            # Rename: remove old, add with new name
            del builder.spec.entities[name]
            builder.spec.entities[new_name] = entity

            # Update root_entity if renamed
            if builder.spec.root_entity == name:
                builder.spec.root_entity = new_name

            # Update editing state
            if builder.editing_entity == name:
                builder.editing_entity = new_name

            # Update references in other entities
            _update_entity_references(builder, name, new_name)

            final_name = new_name

        builder.mark_changed()

        return _entity_editor_response(request, builder, final_name, success=True)

    @router.delete("/entity/{name}", response_class=HTMLResponse)
    async def delete_entity(request: Request, name: str) -> HTMLResponse:
        """Delete an entity."""
        builder = _require_spec()
        _require_entity(builder, name)
        del builder.spec.entities[name]

        # Clear editing state if we were editing this entity
        if builder.editing_entity == name:
            builder.editing_entity = None
            builder.editing_field_idx = None

        # Clear root_entity if it was this entity
        if builder.spec.root_entity == name:
            builder.spec.root_entity = ""

        builder.mark_changed()

        return _entity_list_response(request, builder)


def _update_entity_references(builder: SpecBuilderState, old_name: str, new_name: str) -> None:
    """Update all references to an entity after rename.

    Args:
        builder: The builder state.
        old_name: The old entity name.
        new_name: The new entity name.
    """
    for other_entity in builder.spec.entities.values():
        for field in other_entity.fields:
            # Update items (entity name)
            if field.items == old_name:
                field.items = new_name
            # Update reference (format: Entity.field)
            if field.reference and field.reference.startswith(f"{old_name}."):
                field.reference = f"{new_name}.{field.reference.split('.', 1)[1]}"
            # Update parent_ref (format: Entity.field)
            if field.parent_ref and field.parent_ref.startswith(f"{old_name}."):
                field.parent_ref = f"{new_name}.{field.parent_ref.split('.', 1)[1]}"
