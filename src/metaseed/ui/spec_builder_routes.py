"""Spec Builder routes for the UI.

Provides FastAPI routes for creating and editing ProfileSpec specifications
through an interactive web interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ValidationRuleSpec,
)

from .spec_builder_helpers import (
    clone_spec,
    create_empty_spec,
    list_available_templates,
    save_spec,
    spec_to_yaml,
    validate_entity_name,
    validate_field_name,
)
from .spec_builder_state import SpecBuilderState

if TYPE_CHECKING:
    from .state import AppState

UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"


def create_spec_builder_router(templates: Jinja2Templates, get_state: callable) -> APIRouter:
    """Create the spec builder router with routes.

    Args:
        templates: Jinja2Templates instance.
        get_state: Callable to get AppState.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/spec-builder", tags=["spec-builder"])

    def get_builder_state() -> SpecBuilderState:
        """Get or create spec builder state."""
        state: AppState = get_state()
        if state.spec_builder is None:
            state.spec_builder = SpecBuilderState()
        return state.spec_builder

    # -------------------------------------------------------------------------
    # Main page and start options
    # -------------------------------------------------------------------------

    @router.get("", response_class=HTMLResponse)
    async def spec_builder_index(request: Request) -> HTMLResponse:
        """Render the spec builder main page."""
        builder = get_builder_state()

        if builder.spec is not None:
            # Already working on a spec, show the editor
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

        # Show start options
        available_templates = list_available_templates()
        return templates.TemplateResponse(
            request,
            "spec_builder/start.html",
            {"templates": available_templates},
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

        available_templates = list_available_templates()
        return templates.TemplateResponse(
            request,
            "spec_builder/start.html",
            {"templates": available_templates},
        )

    # -------------------------------------------------------------------------
    # Profile metadata
    # -------------------------------------------------------------------------

    @router.get("/profile-metadata", response_class=HTMLResponse)
    async def get_profile_metadata_form(request: Request) -> HTMLResponse:
        """Get the profile metadata form."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/profile_metadata_form.html",
            {"spec": builder.spec},
        )

    @router.post("/profile-metadata", response_class=HTMLResponse)
    async def update_profile_metadata(
        request: Request,
        name: str = Form(""),
        version: str = Form("1.0"),
        display_name: str = Form(""),
        description: str = Form(""),
        ontology: str = Form(""),
        root_entity: str = Form(""),
    ) -> HTMLResponse:
        """Update profile metadata."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        builder.spec.name = name.strip()
        builder.spec.version = version.strip() or "1.0"
        builder.spec.display_name = display_name.strip() or None
        builder.spec.description = description.strip()
        builder.spec.ontology = ontology.strip() or None
        builder.spec.root_entity = root_entity.strip()
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/profile_metadata_form.html",
            {"spec": builder.spec, "success": True},
        )

    # -------------------------------------------------------------------------
    # Entities management
    # -------------------------------------------------------------------------

    @router.get("/entities", response_class=HTMLResponse)
    async def get_entities_list(request: Request) -> HTMLResponse:
        """Get the entities list panel."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entities_list.html",
            {
                "entities": builder.spec.entities,
                "editing_entity": builder.editing_entity,
                "root_entity": builder.spec.root_entity,
            },
        )

    @router.post("/entity", response_class=HTMLResponse)
    async def add_entity(
        request: Request,
        name: str = Form(...),
    ) -> HTMLResponse:
        """Add a new entity."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        name = name.strip()
        error = validate_entity_name(name)
        if error:
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

        if name in builder.spec.entities:
            return templates.TemplateResponse(
                request,
                "spec_builder/partials/entities_list.html",
                {
                    "entities": builder.spec.entities,
                    "editing_entity": builder.editing_entity,
                    "root_entity": builder.spec.root_entity,
                    "error": f"Entity '{name}' already exists",
                },
            )

        builder.spec.entities[name] = EntityDefSpec(
            ontology_term=None,
            description="",
            fields=[],
        )
        builder.editing_entity = name
        builder.mark_changed()

        # If this is the first entity and no root is set, make it the root
        if not builder.spec.root_entity:
            builder.spec.root_entity = name

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": name,
                "entity": builder.spec.entities[name],
                "editing_field_idx": None,
                "field_types": [t.value for t in FieldType],
            },
        )

    @router.get("/entity/{name}", response_class=HTMLResponse)
    async def get_entity(request: Request, name: str) -> HTMLResponse:
        """Get entity editor form."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")

        builder.editing_entity = name
        builder.editing_field_idx = None

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": name,
                "entity": builder.spec.entities[name],
                "editing_field_idx": None,
                "field_types": [t.value for t in FieldType],
            },
        )

    @router.put("/entity/{name}", response_class=HTMLResponse)
    async def update_entity(
        request: Request,
        name: str,
        description: str = Form(""),
        ontology_term: str = Form(""),
    ) -> HTMLResponse:
        """Update entity metadata."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")

        entity = builder.spec.entities[name]
        entity.description = description.strip()
        entity.ontology_term = ontology_term.strip() or None
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": name,
                "entity": entity,
                "editing_field_idx": None,
                "field_types": [t.value for t in FieldType],
                "success": True,
            },
        )

    @router.delete("/entity/{name}", response_class=HTMLResponse)
    async def delete_entity(request: Request, name: str) -> HTMLResponse:
        """Delete an entity."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")

        del builder.spec.entities[name]

        # Clear editing state if we were editing this entity
        if builder.editing_entity == name:
            builder.editing_entity = None
            builder.editing_field_idx = None

        # Clear root_entity if it was this entity
        if builder.spec.root_entity == name:
            builder.spec.root_entity = ""

        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entities_list.html",
            {
                "entities": builder.spec.entities,
                "editing_entity": builder.editing_entity,
                "root_entity": builder.spec.root_entity,
            },
        )

    # -------------------------------------------------------------------------
    # Fields management
    # -------------------------------------------------------------------------

    @router.post("/entity/{entity_name}/field", response_class=HTMLResponse)
    async def add_field(
        request: Request,
        entity_name: str,
        name: str = Form(...),
        field_type: str = Form("string"),
    ) -> HTMLResponse:
        """Add a new field to an entity."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if entity_name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")

        name = name.strip()
        error = validate_field_name(name)
        if error:
            return templates.TemplateResponse(
                request,
                "spec_builder/partials/entity_editor.html",
                {
                    "spec": builder.spec,
                    "entity_name": entity_name,
                    "entity": builder.spec.entities[entity_name],
                    "editing_field_idx": None,
                    "field_types": [t.value for t in FieldType],
                    "error": error,
                },
            )

        entity = builder.spec.entities[entity_name]

        # Check for duplicate field name
        for f in entity.fields:
            if f.name == name:
                return templates.TemplateResponse(
                    request,
                    "spec_builder/partials/entity_editor.html",
                    {
                        "spec": builder.spec,
                        "entity_name": entity_name,
                        "entity": entity,
                        "editing_field_idx": None,
                        "field_types": [t.value for t in FieldType],
                        "error": f"Field '{name}' already exists",
                    },
                )

        new_field = FieldSpec(
            name=name,
            type=FieldType(field_type),
            required=False,
            description="",
        )
        entity.fields.append(new_field)
        builder.editing_field_idx = len(entity.fields) - 1
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": entity_name,
                "entity": entity,
                "editing_field_idx": builder.editing_field_idx,
                "field_types": [t.value for t in FieldType],
            },
        )

    @router.get("/entity/{entity_name}/field/{idx}", response_class=HTMLResponse)
    async def get_field_form(request: Request, entity_name: str, idx: int) -> HTMLResponse:
        """Get field editor form."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if entity_name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")

        entity = builder.spec.entities[entity_name]
        if idx < 0 or idx >= len(entity.fields):
            raise HTTPException(status_code=404, detail="Field not found")

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
        codename: str = Form(""),
        items: str = Form(""),
        parent_ref: str = Form(""),
        pattern: str = Form(""),
        min_length: str = Form(""),
        max_length: str = Form(""),
        minimum: str = Form(""),
        maximum: str = Form(""),
        enum_values: str = Form(""),
    ) -> HTMLResponse:
        """Update a field."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if entity_name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")

        entity = builder.spec.entities[entity_name]
        if idx < 0 or idx >= len(entity.fields):
            raise HTTPException(status_code=404, detail="Field not found")

        # Build constraints if any are provided
        constraints = None
        has_constraints = any([pattern, min_length, max_length, minimum, maximum, enum_values])
        if has_constraints:
            constraints = Constraints(
                pattern=pattern.strip() or None,
                min_length=int(min_length) if min_length.strip() else None,
                max_length=int(max_length) if max_length.strip() else None,
                minimum=float(minimum) if minimum.strip() else None,
                maximum=float(maximum) if maximum.strip() else None,
                enum=[v.strip() for v in enum_values.split("\n") if v.strip()]
                if enum_values.strip()
                else None,
            )

        # Update field
        field = entity.fields[idx]
        field.name = name.strip()
        field.type = FieldType(field_type)
        field.required = required
        field.description = description.strip()
        field.ontology_term = ontology_term.strip() or None
        field.codename = codename.strip() or None
        field.items = items.strip() or None
        field.parent_ref = parent_ref.strip() or None
        field.constraints = constraints

        builder.editing_field_idx = None
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": entity_name,
                "entity": entity,
                "editing_field_idx": None,
                "field_types": [t.value for t in FieldType],
                "success": True,
            },
        )

    @router.delete("/entity/{entity_name}/field/{idx}", response_class=HTMLResponse)
    async def delete_field(request: Request, entity_name: str, idx: int) -> HTMLResponse:
        """Delete a field from an entity."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if entity_name not in builder.spec.entities:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")

        entity = builder.spec.entities[entity_name]
        if idx < 0 or idx >= len(entity.fields):
            raise HTTPException(status_code=404, detail="Field not found")

        del entity.fields[idx]
        builder.editing_field_idx = None
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/entity_editor.html",
            {
                "spec": builder.spec,
                "entity_name": entity_name,
                "entity": entity,
                "editing_field_idx": None,
                "field_types": [t.value for t in FieldType],
            },
        )

    # -------------------------------------------------------------------------
    # Validation rules management
    # -------------------------------------------------------------------------

    @router.get("/validation-rules", response_class=HTMLResponse)
    async def get_validation_rules(request: Request) -> HTMLResponse:
        """Get validation rules list."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rules_list.html",
            {
                "rules": builder.spec.validation_rules,
                "editing_rule_idx": builder.editing_rule_idx,
                "entities": list(builder.spec.entities.keys()),
            },
        )

    @router.post("/validation-rule", response_class=HTMLResponse)
    async def add_validation_rule(
        request: Request,
        name: str = Form(...),
    ) -> HTMLResponse:
        """Add a new validation rule."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        name = name.strip()
        if not name:
            return templates.TemplateResponse(
                request,
                "spec_builder/partials/validation_rules_list.html",
                {
                    "rules": builder.spec.validation_rules,
                    "editing_rule_idx": None,
                    "entities": list(builder.spec.entities.keys()),
                    "error": "Rule name is required",
                },
            )

        new_rule = ValidationRuleSpec(
            name=name,
            description="",
            applies_to="all",
        )
        builder.spec.validation_rules.append(new_rule)
        builder.editing_rule_idx = len(builder.spec.validation_rules) - 1
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rule_form.html",
            {
                "rule": new_rule,
                "rule_idx": builder.editing_rule_idx,
                "entities": list(builder.spec.entities.keys()),
            },
        )

    @router.get("/validation-rule/{idx}", response_class=HTMLResponse)
    async def get_validation_rule_form(request: Request, idx: int) -> HTMLResponse:
        """Get validation rule editor form."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if idx < 0 or idx >= len(builder.spec.validation_rules):
            raise HTTPException(status_code=404, detail="Rule not found")

        builder.editing_rule_idx = idx

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rule_form.html",
            {
                "rule": builder.spec.validation_rules[idx],
                "rule_idx": idx,
                "entities": list(builder.spec.entities.keys()),
            },
        )

    @router.put("/validation-rule/{idx}", response_class=HTMLResponse)
    async def update_validation_rule(
        request: Request,
        idx: int,
        name: str = Form(...),
        description: str = Form(""),
        applies_to: str = Form("all"),
        field: str = Form(""),
        condition: str = Form(""),
        pattern: str = Form(""),
        minimum: str = Form(""),
        maximum: str = Form(""),
        enum_values: str = Form(""),
        reference: str = Form(""),
        unique_within: str = Form(""),
        min_items: str = Form(""),
        max_items: str = Form(""),
    ) -> HTMLResponse:
        """Update a validation rule."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if idx < 0 or idx >= len(builder.spec.validation_rules):
            raise HTTPException(status_code=404, detail="Rule not found")

        rule = builder.spec.validation_rules[idx]

        # Parse applies_to (can be "all" or comma-separated entity names)
        applies_to = applies_to.strip()
        if applies_to == "all":
            applies_to_value: str | list[str] = "all"
        else:
            applies_to_value = [e.strip() for e in applies_to.split(",") if e.strip()]
            if len(applies_to_value) == 1:
                applies_to_value = applies_to_value[0]

        rule.name = name.strip()
        rule.description = description.strip()
        rule.applies_to = applies_to_value
        rule.field = field.strip() or None
        rule.condition = condition.strip() or None
        rule.pattern = pattern.strip() or None
        rule.minimum = float(minimum) if minimum.strip() else None
        rule.maximum = float(maximum) if maximum.strip() else None
        rule.enum = (
            [v.strip() for v in enum_values.split("\n") if v.strip()]
            if enum_values.strip()
            else None
        )
        rule.reference = reference.strip() or None
        rule.unique_within = unique_within.strip() or None
        rule.min_items = int(min_items) if min_items.strip() else None
        rule.max_items = int(max_items) if max_items.strip() else None

        builder.editing_rule_idx = None
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rules_list.html",
            {
                "rules": builder.spec.validation_rules,
                "editing_rule_idx": None,
                "entities": list(builder.spec.entities.keys()),
                "success": True,
            },
        )

    @router.delete("/validation-rule/{idx}", response_class=HTMLResponse)
    async def delete_validation_rule(request: Request, idx: int) -> HTMLResponse:
        """Delete a validation rule."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if idx < 0 or idx >= len(builder.spec.validation_rules):
            raise HTTPException(status_code=404, detail="Rule not found")

        del builder.spec.validation_rules[idx]
        builder.editing_rule_idx = None
        builder.mark_changed()

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rules_list.html",
            {
                "rules": builder.spec.validation_rules,
                "editing_rule_idx": None,
                "entities": list(builder.spec.entities.keys()),
            },
        )

    # -------------------------------------------------------------------------
    # Preview and export
    # -------------------------------------------------------------------------

    @router.get("/preview", response_class=HTMLResponse)
    async def preview_yaml(request: Request) -> HTMLResponse:
        """Get YAML preview of the current spec."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        yaml_content = spec_to_yaml(builder.spec)

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/yaml_preview.html",
            {"yaml_content": yaml_content},
        )

    @router.get("/export")
    async def export_yaml(_request: Request) -> StreamingResponse:
        """Download the spec as a YAML file."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        yaml_content = spec_to_yaml(builder.spec)
        filename = f"{builder.spec.name or 'profile'}.yaml"

        return StreamingResponse(
            iter([yaml_content]),
            media_type="application/x-yaml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/save", response_class=HTMLResponse)
    async def save_to_filesystem(request: Request) -> HTMLResponse:
        """Save the spec to the specs directory."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        if not builder.spec.name:
            return templates.TemplateResponse(
                request,
                "spec_builder/partials/save_result.html",
                {"error": "Profile name is required before saving"},
            )

        try:
            saved_path = save_spec(builder.spec)
            builder.mark_saved()
            return templates.TemplateResponse(
                request,
                "spec_builder/partials/save_result.html",
                {"success": True, "path": str(saved_path)},
            )
        except Exception as e:
            return templates.TemplateResponse(
                request,
                "spec_builder/partials/save_result.html",
                {"error": str(e)},
            )

    return router
