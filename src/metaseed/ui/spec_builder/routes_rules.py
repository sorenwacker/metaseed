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

from metaseed.specs.predicates import render_predicate
from metaseed.specs.schema import ValidationRuleSpec

from .predicate_form import (
    OPERATORS,
    list_field_options,
    predicate_from_rows,
    rows_from_predicate,
)

if TYPE_CHECKING:
    from .state import SpecBuilderState


class RuleUpdateData(BaseModel):
    """Data for updating a validation rule. Reduces parameter count."""

    name: str
    description: str = ""
    rule_type: str = ""
    message: str = ""
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
    lat_field: str = ""
    lon_field: str = ""
    start_field: str = ""
    end_field: str = ""
    where_join: str = "all"
    where_keep: str = ""
    when_join: str = "all"
    when_keep: str = ""
    when_fields: list[str] = []
    when_ops: list[str] = []
    when_values: list[str] = []
    require: str = ""
    where_fields: list[str] = []
    where_ops: list[str] = []
    where_values: list[str] = []

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
        rule.type = self.rule_type.strip() or None
        rule.message = self.message.strip() or None
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
        rule.lat_field = self.lat_field.strip() or None
        rule.lon_field = self.lon_field.strip() or None
        rule.start_field = self.start_field.strip() or None
        rule.end_field = self.end_field.strip() or None
        if not self.where_keep:
            rule.where = predicate_from_rows(
                self.where_join, self.where_fields, self.where_ops, self.where_values
            )
        if not self.when_keep:
            rule.when = predicate_from_rows(
                self.when_join, self.when_fields, self.when_ops, self.when_values
            )
        rule.require = [
            name.strip() for name in self.require.split(",") if name.strip()
        ] or None


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
        _base_url: Base URL prefix for all links (no trailing slash).
    """

    def _require_spec() -> SpecBuilderState:
        """Get builder state, raising HTTPException if no spec in progress."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")
        return builder

    def _require_rule(builder: SpecBuilderState, idx: int) -> ValidationRuleSpec:
        """Get rule by index, raising HTTPException if not found."""
        assert builder.spec is not None  # caller resolves via _require_spec
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
        assert builder.spec is not None  # caller resolves via _require_spec
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rules_list.html",
            {
                "rules": builder.spec.validation_rules,
                # Rendered here rather than in the template: the one-line
                # spelling is what a rule reads as, and it exists exactly once.
                "predicates": {
                    index: render_predicate(rule.where)
                    for index, rule in enumerate(builder.spec.validation_rules)
                    if rule.where is not None
                },
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
        error: str | None = None,
        typed_rows: tuple[str, list[dict[str, object]]] | None = None,
    ) -> HTMLResponse:
        """Helper to return rule form template response."""
        assert builder.spec is not None  # caller resolves via _require_spec
        # On the error path the rows come back from what was posted, not from
        # the stored rule: a predicate is fiddly enough that losing the typing
        # to report one bad value would be worse than the mistake.
        editable = typed_rows or rows_from_predicate(rule.where)
        requirement = rows_from_predicate(rule.when)
        return templates.TemplateResponse(
            request,
            "spec_builder/partials/validation_rule_form.html",
            {
                "rule": rule,
                "rule_idx": idx,
                "entities": list(builder.spec.entities.keys()),
                "list_fields": list_field_options(builder.spec),
                "operators": OPERATORS,
                # None means the stored predicate nests deeper than rows can
                # express: shown as its one-line spelling and left untouched
                # rather than flattened into something else.
                "where_join": editable[0] if editable else "all",
                "where_rows": editable[1] if editable else None,
                "where_text": render_predicate(rule.where) if rule.where else "",
                "when_join": requirement[0] if requirement else "all",
                "when_rows": requirement[1] if requirement else None,
                "when_text": render_predicate(rule.when) if rule.when else "",
                "error": error,
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
        assert builder.spec is not None  # _require_spec guarantees spec is set

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
        rule_type: str = Form(""),
        message: str = Form(""),
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
        lat_field: str = Form(""),
        lon_field: str = Form(""),
        start_field: str = Form(""),
        end_field: str = Form(""),
        where_join: str = Form("all"),
        where_keep: str = Form(""),
        when_join: str = Form("all"),
        when_keep: str = Form(""),
        when_field: list[str] = Form([]),
        when_op: list[str] = Form([]),
        when_value: list[str] = Form([]),
        require: str = Form(""),
        where_field: list[str] = Form([]),
        where_op: list[str] = Form([]),
        where_value: list[str] = Form([]),
    ) -> HTMLResponse:
        """Update a validation rule."""
        builder = _require_spec()
        rule = _require_rule(builder, idx)

        # Use RuleUpdateData to apply changes
        update_data = RuleUpdateData(
            name=name,
            description=description,
            rule_type=rule_type,
            message=message,
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
            lat_field=lat_field,
            lon_field=lon_field,
            start_field=start_field,
            end_field=end_field,
            where_join=where_join,
            where_keep=where_keep,
            when_join=when_join,
            when_keep=when_keep,
            when_fields=when_field,
            when_ops=when_op,
            when_values=when_value,
            require=require,
            where_fields=where_field,
            where_ops=where_op,
            where_values=where_value,
        )
        try:
            update_data.apply_to_rule(rule)
        except ValueError as exc:
            # Back to the form with what was typed still in it: a predicate row
            # is fiddly enough that discarding the whole edit to report one bad
            # value would be worse than the mistake.
            return _rule_form_response(
                request,
                builder,
                rule,
                idx,
                error=str(exc),
                typed_rows=(
                    where_join,
                    [
                        {"field": f, "op": o, "value": v}
                        for f, o, v in zip(
                            where_field, where_op, where_value, strict=False
                        )
                    ],
                ),
            )

        builder.editing_rule_idx = None
        builder.mark_changed()

        return _rules_list_response(request, builder, success=True)

    @router.delete("/validation-rule/{idx}", response_class=HTMLResponse)
    async def delete_validation_rule(request: Request, idx: int) -> HTMLResponse:
        """Delete a validation rule."""
        builder = _require_spec()
        _require_rule(builder, idx)  # Validate idx exists

        assert builder.spec is not None  # _require_spec guarantees spec is set
        del builder.spec.validation_rules[idx]
        builder.editing_rule_idx = None
        builder.mark_changed()

        return _rules_list_response(request, builder)
