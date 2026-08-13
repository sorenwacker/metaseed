"""Field management routes for the Spec Builder.

Handles CRUD operations for fields within entities.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.field_form import FieldForm
from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType
from metaseed.ui.spec_builder.access import (
    entity_editor_response,
    require_entity,
    require_spec,
)

if TYPE_CHECKING:
    from .state import SpecBuilderState


def register_field_routes(
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
    _base_url: str = "",
) -> None:
    """Register field management routes.

    Args:
        router: The APIRouter to add routes to.
        templates: Jinja2Templates instance.
        get_builder_state: Callable to get builder state.
        _base_url: Base URL prefix for all links (no trailing slash).
    """

    def _require_spec() -> SpecBuilderState:
        return require_spec(get_builder_state)

    _require_entity = require_entity

    def _require_field(entity: EntityDefSpec, idx: int) -> FieldSpec:
        """Get field by index, raising HTTPException if not found."""
        if idx < 0 or idx >= len(entity.fields):
            raise HTTPException(status_code=404, detail="Field not found")
        return entity.fields[idx]

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

    @router.post("/entity/{entity_name}/field", response_class=HTMLResponse)
    async def add_field(
        request: Request,
        entity_name: str,
        name: str = Form(...),
        field_type: str = Form("string"),
        items: str = Form(""),
    ) -> HTMLResponse:
        """Add a new field to an entity."""
        builder = _require_spec()
        assert builder.spec is not None  # _require_spec guarantees spec is set
        _require_entity(builder, entity_name)
        name = name.strip()
        try:
            # add_field also creates the parent identifier and target
            # back-reference for nested fields.
            SpecBuilder.from_spec(builder.spec).add_field(
                entity_name, name, field_type, items=items.strip() or None
            )
        except ValueError as error:
            return _entity_editor_response(
                request, builder, entity_name, error=str(error)
            )

        entity = builder.spec.entities[entity_name]
        builder.editing_field_idx = next(
            i for i, f in enumerate(entity.fields) if f.name == name
        )
        builder.mark_changed()

        return _entity_editor_response(request, builder, entity_name)

    @router.get("/entity/{entity_name}/field/{idx}", response_class=HTMLResponse)
    async def get_field_form(
        request: Request, entity_name: str, idx: int
    ) -> HTMLResponse:
        """Get field editor form."""
        builder = _require_spec()
        entity = _require_entity(builder, entity_name)
        _require_field(entity, idx)
        builder.editing_field_idx = idx

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/field_form.html",
            {
                "spec": builder.spec,
                "entity_name": entity_name,
                "field": entity.fields[idx],
                "field_idx": idx,
                "field_types": [t.value for t in FieldType],
            },
        )

    @router.put("/entity/{entity_name}/field/{idx}", response_class=HTMLResponse)
    async def update_field(
        request: Request,
        entity_name: str,
        idx: int,
        name: str = Form(...),
        field_type: str = Form("string"),
        required: bool = Form(False),
        description: str = Form(""),
        ontology_term: str = Form(""),
        ontologies: str = Form(""),
        within: str = Form(""),
        codename: str = Form(""),
        items: str = Form(""),
        parent_ref: str = Form(""),
        pattern: str = Form(""),
        min_length: str = Form(""),
        max_length: str = Form(""),
        minimum: str = Form(""),
        maximum: str = Form(""),
        min_items: str = Form(""),
        max_items: str = Form(""),
        enum_values: str = Form(""),
        unique_within: str = Form(""),
        reference_scope: str = Form(""),
        reference: str = Form(""),
        owns: bool = Form(False),
        is_identifier: bool = Form(False),
        is_label: bool = Form(False),
        tier: str = Form(""),
        label: str = Form(""),
        unit: str = Form(""),
        example: str = Form(""),
        options: str = Form(""),
        dcat: str = Form(""),
    ) -> HTMLResponse:
        """Update a field."""
        builder = _require_spec()
        entity = _require_entity(builder, entity_name)
        _require_field(entity, idx)

        # Map the form to the field via the shared, pure FieldForm mapping so the
        # form -> FieldSpec logic (all markers) lives in one place.
        #
        # This deliberately *replaces* the constraints rather than merging them
        # (SpecBuilder.update_field_constraints). The field editor renders an
        # input for every constraint and posts all of them on every save, so an
        # empty box means the user cleared that constraint, not that it is
        # unchanged. Merging here would make constraints impossible to remove
        # from the UI. FieldForm.build_constraints collapses an all-empty form to
        # None, matching the merge path's rule that no constraints means no
        # constraints block.
        form = FieldForm(
            name=name,
            field_type=field_type,
            required=required,
            description=description,
            ontology_term=ontology_term,
            ontologies=ontologies,
            within=within,
            codename=codename,
            items=items,
            parent_ref=parent_ref,
            pattern=pattern,
            min_length=min_length,
            max_length=max_length,
            minimum=minimum,
            maximum=maximum,
            min_items=min_items,
            max_items=max_items,
            enum_values=enum_values,
            unique_within=unique_within,
            reference_scope=reference_scope,
            reference=reference,
            owns=owns,
            is_identifier=is_identifier,
            is_label=is_label,
            tier=tier,
            label=label,
            unit=unit,
            example=example,
            options=options,
            dcat=dcat,
        )

        # Applied to a copy and swapped in on success: `apply_to` assigns field
        # by field, so a bad value mid-way (an invalid field_type, a malformed
        # constraint) used to leave the stored field half-edited — and the
        # route had no error handling at all, so the person saw a 500 and the
        # draft kept the damage.
        try:
            updated = entity.fields[idx].model_copy(deep=True)
            form.apply_to(updated)
        except (ValueError, TypeError) as exc:
            return _entity_editor_response(
                request, builder, entity_name, error=f"Field not saved: {exc}"
            )
        entity.fields[idx] = updated

        builder.editing_field_idx = None
        builder.mark_changed()

        return _entity_editor_response(request, builder, entity_name, success=True)

    @router.delete("/entity/{entity_name}/field/{idx}", response_class=HTMLResponse)
    async def delete_field(
        request: Request, entity_name: str, idx: int
    ) -> HTMLResponse:
        """Delete a field from an entity."""
        builder = _require_spec()
        entity = _require_entity(builder, entity_name)
        _require_field(entity, idx)
        del entity.fields[idx]
        builder.editing_field_idx = None
        builder.mark_changed()

        return _entity_editor_response(request, builder, entity_name)

    @router.post(
        "/entity/{entity_name}/field/{idx}/move-up", response_class=HTMLResponse
    )
    async def move_field_up(
        request: Request, entity_name: str, idx: int
    ) -> HTMLResponse:
        """Move a field up in the list."""
        builder = _require_spec()
        entity = _require_entity(builder, entity_name)
        _require_field(entity, idx)

        if idx > 0:
            entity.fields[idx], entity.fields[idx - 1] = (
                entity.fields[idx - 1],
                entity.fields[idx],
            )
            builder.mark_changed()

        return _entity_editor_response(request, builder, entity_name)

    @router.post(
        "/entity/{entity_name}/field/{idx}/move-down", response_class=HTMLResponse
    )
    async def move_field_down(
        request: Request, entity_name: str, idx: int
    ) -> HTMLResponse:
        """Move a field down in the list."""
        builder = _require_spec()
        entity = _require_entity(builder, entity_name)
        _require_field(entity, idx)

        if idx < len(entity.fields) - 1:
            entity.fields[idx], entity.fields[idx + 1] = (
                entity.fields[idx + 1],
                entity.fields[idx],
            )
            builder.mark_changed()

        return _entity_editor_response(request, builder, entity_name)
