"""Validation rules management routes for the Spec Builder.

Handles CRUD operations for validation rules within a specification.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.schema import ValidationRuleSpec

if TYPE_CHECKING:
    from .state import SpecBuilderState


def register_rule_routes(
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
) -> None:
    """Register validation rule management routes.

    Args:
        router: The APIRouter to add routes to.
        templates: Jinja2Templates instance.
        get_builder_state: Callable to get builder state.
    """

    def _rules_list_response(
        request: Request,
        builder: SpecBuilderState,
        error: str | None = None,
        success: bool = False,
    ) -> HTMLResponse:
        """Helper to return rules list template response."""
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rules_list.html",
            {
                "rules": builder.spec.validation_rules,
                "editing_rule_idx": builder.editing_rule_idx,
                "entities": list(builder.spec.entities.keys()),
                "error": error,
                "success": success,
            },
        )

    @router.get("/validation-rules", response_class=HTMLResponse)
    async def get_validation_rules(request: Request) -> HTMLResponse:
        """Get validation rules list."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")

        return _rules_list_response(request, builder)

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
            return _rules_list_response(request, builder, error="Rule name is required")

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
        applies_to_value: str | list[str]
        if applies_to == "all":
            applies_to_value = "all"
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

        return _rules_list_response(request, builder, success=True)

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

        return _rules_list_response(request, builder)
