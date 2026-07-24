"""Field management routes for the Spec Builder.

Handles CRUD operations for fields within entities.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.schema import Constraints, EntityDefSpec, FieldSpec, FieldType

if TYPE_CHECKING:
    from .state import SpecBuilderState


class FieldUpdateData(BaseModel):
    """Data for updating a field. Reduces parameter count."""

    name: str
    field_type: str = "string"
    required: bool = False
    description: str = ""
    ontology_term: str = ""
    codename: str = ""
    items: str = ""
    parent_ref: str = ""
    pattern: str = ""
    min_length: str = ""
    max_length: str = ""
    minimum: str = ""
    maximum: str = ""
    min_items: str = ""
    max_items: str = ""
    enum_values: str = ""
    unique_within: str = ""
    reference: str = ""

    def build_constraints(self) -> Constraints | None:
        """Build Constraints object from form data."""
        has_constraints = any(
            [
                self.pattern,
                self.min_length,
                self.max_length,
                self.minimum,
                self.maximum,
                self.min_items,
                self.max_items,
                self.enum_values,
            ]
        )
        if not has_constraints:
            return None

        return Constraints(
            pattern=self.pattern.strip() or None,
            min_length=int(self.min_length) if self.min_length.strip() else None,
            max_length=int(self.max_length) if self.max_length.strip() else None,
            minimum=float(self.minimum) if self.minimum.strip() else None,
            maximum=float(self.maximum) if self.maximum.strip() else None,
            min_items=int(self.min_items) if self.min_items.strip() else None,
            max_items=int(self.max_items) if self.max_items.strip() else None,
            enum=[v.strip() for v in self.enum_values.split("\n") if v.strip()]
            if self.enum_values.strip()
            else None,
        )


def register_field_routes(  # noqa: C901
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
        """Get builder state, raising HTTPException if no spec in progress."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")
        return builder

    def _require_entity(builder: SpecBuilderState, name: str) -> EntityDefSpec:
        """Get entity by name, raising HTTPException if not found."""
        assert builder.spec is not None  # caller resolves via _require_spec
        if name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
        return builder.spec.entities[name]

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
        """Helper to return entity editor template response."""
        assert builder.spec is not None  # caller resolves via _require_spec
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
        reference: str = Form(""),
        owns: bool = Form(False),
        is_identifier: bool = Form(False),
        is_label: bool = Form(False),
        tier: str = Form(""),
        label: str = Form(""),
        unit: str = Form(""),
        example: str = Form(""),
        options: str = Form(""),
    ) -> HTMLResponse:
        """Update a field."""
        builder = _require_spec()
        entity = _require_entity(builder, entity_name)
        _require_field(entity, idx)

        # Build update data and constraints
        update_data = FieldUpdateData(
            name=name,
            field_type=field_type,
            required=required,
            description=description,
            ontology_term=ontology_term,
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
            reference=reference,
        )

        # Update field
        field = entity.fields[idx]
        field.name = update_data.name.strip()
        field.type = FieldType(update_data.field_type)
        field.required = update_data.required
        field.description = update_data.description.strip()
        field.ontology_term = update_data.ontology_term.strip() or None
        # Parse ontologies from comma-separated string
        ontologies_list = [o.strip() for o in ontologies.split(",") if o.strip()]
        field.ontologies = ontologies_list or None
        field.codename = update_data.codename.strip() or None
        field.items = update_data.items.strip() or None
        field.parent_ref = update_data.parent_ref.strip() or None
        field.unique_within = update_data.unique_within.strip() or None
        field.reference = update_data.reference.strip() or None
        field.constraints = update_data.build_constraints()
        # spec_version 0.6 markers (#137/#143/#98). Booleans default to None
        # rather than False so an unset marker is dropped on serialization.
        field.owns = owns or None
        field.is_identifier = is_identifier or None
        field.is_label = is_label or None
        tier_value = tier.strip()
        field.tier = (
            tier_value  # type: ignore[assignment]
            if tier_value in ("required", "recommended", "optional")
            else None
        )
        field.label = label.strip() or None
        field.unit = unit.strip() or None
        field.example = example.strip() or None
        field.options = [o.strip() for o in options.split(",") if o.strip()] or None

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
