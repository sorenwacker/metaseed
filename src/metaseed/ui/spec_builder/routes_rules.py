"""Validation rules management routes for the Spec Builder.

Handles CRUD operations for validation rules within a specification.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from metaseed.specs.schema import ValidationRuleSpec

if TYPE_CHECKING:
    from .state import SpecBuilderState


class RuleUpdateData(BaseModel):
    """Data for updating a validation rule. Reduces parameter count."""

    name: str
    description: str = ""
    applies_to: str = "all"
    field: str = ""
    condition: str = ""
    pattern: str = ""
    minimum: str = ""
    maximum: str = ""
    enum_values: str = ""
    reference: str = ""
    unique_within: str = ""
    min_items: str = ""
    max_items: str = ""

    def parse_applies_to(self) -> str | list[str]:
        """Parse applies_to into proper format."""
        applies_to = self.applies_to.strip()
        if applies_to == "all":
            return "all"
        values = [e.strip() for e in applies_to.split(",") if e.strip()]
        if len(values) == 1:
            return values[0]
        return values

    def apply_to_rule(self, rule: ValidationRuleSpec) -> None:
        """Apply update data to a validation rule."""
        rule.name = self.name.strip()
        rule.description = self.description.strip()
        rule.applies_to = self.parse_applies_to()
        rule.field = self.field.strip() or None
        rule.condition = self.condition.strip() or None
        rule.pattern = self.pattern.strip() or None
        rule.minimum = float(self.minimum) if self.minimum.strip() else None
        rule.maximum = float(self.maximum) if self.maximum.strip() else None
        rule.enum = (
            [v.strip() for v in self.enum_values.split("\n") if v.strip()]
            if self.enum_values.strip()
            else None
        )
        rule.reference = self.reference.strip() or None
        rule.unique_within = self.unique_within.strip() or None
        rule.min_items = int(self.min_items) if self.min_items.strip() else None
        rule.max_items = int(self.max_items) if self.max_items.strip() else None


def register_rule_routes(
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
    _base_url: str = "",
) -> None:
    """Register validation rule management routes.

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

    def _require_rule(builder: SpecBuilderState, idx: int) -> ValidationRuleSpec:
        """Get rule by index, raising HTTPException if not found."""
        if idx < 0 or idx >= len(builder.spec.validation_rules):
            raise HTTPException(status_code=404, detail="Rule not found")
        return builder.spec.validation_rules[idx]

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

    def _rule_form_response(
        request: Request,
        builder: SpecBuilderState,
        rule: ValidationRuleSpec,
        idx: int,
    ) -> HTMLResponse:
        """Helper to return rule form template response."""
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rule_form.html",
            {
                "rule": rule,
                "rule_idx": idx,
                "entities": list(builder.spec.entities.keys()),
            },
        )

    @router.get("/validation-rules", response_class=HTMLResponse)
    async def get_validation_rules(request: Request) -> HTMLResponse:
        """Get validation rules list."""
        builder = _require_spec()
        return _rules_list_response(request, builder)

    @router.post("/validation-rule", response_class=HTMLResponse)
    async def add_validation_rule(
        request: Request,
        name: str = Form(...),
    ) -> HTMLResponse:
        """Add a new validation rule."""
        builder = _require_spec()

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

        return _rule_form_response(request, builder, new_rule, builder.editing_rule_idx)

    @router.get("/validation-rule/{idx}", response_class=HTMLResponse)
    async def get_validation_rule_form(request: Request, idx: int) -> HTMLResponse:
        """Get validation rule editor form."""
        builder = _require_spec()
        rule = _require_rule(builder, idx)
        builder.editing_rule_idx = idx
        return _rule_form_response(request, builder, rule, idx)

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
        builder = _require_spec()
        rule = _require_rule(builder, idx)

        # Use RuleUpdateData to apply changes
        update_data = RuleUpdateData(
            name=name,
            description=description,
            applies_to=applies_to,
            field=field,
            condition=condition,
            pattern=pattern,
            minimum=minimum,
            maximum=maximum,
            enum_values=enum_values,
            reference=reference,
            unique_within=unique_within,
            min_items=min_items,
            max_items=max_items,
        )
        update_data.apply_to_rule(rule)

        builder.editing_rule_idx = None
        builder.mark_changed()

        return _rules_list_response(request, builder, success=True)

    @router.delete("/validation-rule/{idx}", response_class=HTMLResponse)
    async def delete_validation_rule(request: Request, idx: int) -> HTMLResponse:
        """Delete a validation rule."""
        builder = _require_spec()
        _require_rule(builder, idx)  # Validate idx exists

        del builder.spec.validation_rules[idx]
        builder.editing_rule_idx = None
        builder.mark_changed()

        return _rules_list_response(request, builder)
