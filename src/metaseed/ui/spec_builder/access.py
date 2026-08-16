"""Helpers the spec-builder route registrars share.

``_require_spec`` and ``_require_entity`` were defined identically inside both
``register_entity_routes`` and ``register_field_routes`` — an undocumented copy
the duplication gate found. They live once, here, taking what the closures
captured as arguments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from metaseed.seek.roles import SEEK_ROLES
from metaseed.specs.schema import FieldType

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import Request
    from fastapi.templating import Jinja2Templates

    from metaseed.specs.schema import EntityDefSpec

    from .state import SpecBuilderState


def require_spec(get_builder_state: Callable[[], SpecBuilderState]) -> SpecBuilderState:
    """The builder state, or 400 if no spec is in progress."""
    builder = get_builder_state()
    if builder.spec is None:
        raise HTTPException(status_code=400, detail="No spec in progress")
    return builder


def require_entity(builder: SpecBuilderState, name: str) -> EntityDefSpec:
    """The named entity, or 404."""
    assert builder.spec is not None  # caller resolves via require_spec
    if name not in builder.spec.entities:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return builder.spec.entities[name]


def entity_editor_response(
    templates: Jinja2Templates,
    request: Request,
    builder: SpecBuilderState,
    entity_name: str,
    error: str | None = None,
    success: bool = False,
) -> HTMLResponse:
    """Render the entity editor panel.

    One renderer for both the entity and the field routes. When each had its
    own copy, the field routes' omitted ``seek_roles`` — same template, so the
    role dropdown rendered from an undefined variable after a field save.
    """
    assert builder.spec is not None  # caller resolves via require_spec
    return templates.TemplateResponse(
        request,
        "spec_builder/partials/entity_editor.html",
        {
            "spec": builder.spec,
            "entity_name": entity_name,
            "entity": builder.spec.entities[entity_name],
            "editing_field_idx": builder.editing_field_idx,
            "field_types": [t.value for t in FieldType],
            "seek_roles": SEEK_ROLES,
            "error": error,
            "success": success,
        },
    )
