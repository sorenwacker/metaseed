"""Spec Builder package for creating and editing ProfileSpec specifications.

This package provides FastAPI routes organized by resource type:
- entities: Entity CRUD operations
- fields: Field CRUD operations
- rules: Validation rules CRUD
- export: Preview, export, and save operations
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

from .routes_entities import register_entity_routes
from .routes_export import register_export_routes
from .routes_fields import register_field_routes
from .routes_main import register_main_routes
from .routes_rules import register_rule_routes
from .state import SpecBuilderState

if TYPE_CHECKING:
    from ..state import AppState

__all__ = ["SpecBuilderState", "create_spec_builder_router"]


def create_spec_builder_router(templates: Jinja2Templates, get_state: callable) -> APIRouter:
    """Create the spec builder router with all routes.

    Args:
        templates: Jinja2Templates instance.
        get_state: Callable to get AppState.

    Returns:
        Configured APIRouter with all spec builder routes.
    """
    router = APIRouter(prefix="/spec-builder", tags=["spec-builder"])

    def get_builder_state() -> SpecBuilderState:
        """Get or create spec builder state."""
        state: AppState = get_state()
        if state.spec_builder is None:
            state.spec_builder = SpecBuilderState()
        return state.spec_builder

    # Register all route groups
    register_main_routes(router, templates, get_builder_state)
    register_entity_routes(router, templates, get_builder_state)
    register_field_routes(router, templates, get_builder_state)
    register_rule_routes(router, templates, get_builder_state)
    register_export_routes(router, templates, get_builder_state)

    return router
