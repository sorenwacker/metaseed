"""Validation routes for form validation.

Provides routes for validating form data against profile specs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from metaseed.facade import ProfileFacade
from metaseed.validators import validate as validate_data

from ..helpers import collect_form_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState


def register_validation_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
) -> None:
    """Register validation routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.post("/validate", response_class=HTMLResponse)
    async def validate_form(request: Request) -> HTMLResponse:
        """Validate form data against MIAPPE spec."""
        state = get_state()
        form_data = await request.form()
        entity_type = form_data.get("_entity_type")

        if not entity_type:
            return templates.TemplateResponse(
                request,
                "components/validation_result.html",
                {
                    "valid": False,
                    "errors": [
                        {
                            "field": "_entity_type",
                            "message": "Entity type is required",
                            "rule": "required",
                        }
                    ],
                },
            )

        facade = ProfileFacade(profile=state.profile)
        helper = getattr(facade, entity_type)
        values = collect_form_values(dict(form_data), helper)

        for field_name, items in state.current_nested_items.items():
            if items:
                values[field_name] = items

        errors = []
        if state.profile == "miappe":
            errors = validate_data(values, entity_type, version=facade.version)

        error_list = [{"field": e.field, "message": e.message, "rule": e.rule} for e in errors]

        return templates.TemplateResponse(
            request,
            "components/validation_result.html",
            {"valid": len(errors) == 0, "errors": error_list},
        )
