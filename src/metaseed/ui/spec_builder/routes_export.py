"""Export and save routes for the Spec Builder.

Handles preview, export, save, and graph data operations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

from ..spec_builder_helpers import delete_user_spec, save_spec, spec_to_yaml

if TYPE_CHECKING:
    from .state import SpecBuilderState


def register_export_routes(
    router: APIRouter,
    templates: Jinja2Templates,
    get_builder_state: Callable[[], SpecBuilderState],
) -> None:
    """Register export and save routes.

    Args:
        router: The APIRouter to add routes to.
        templates: Jinja2Templates instance.
        get_builder_state: Callable to get builder state.
    """

    def _require_spec() -> SpecBuilderState:
        """Get builder state, raising HTTPException if no spec in progress."""
        builder = get_builder_state()
        if builder.spec is None:
            raise HTTPException(status_code=400, detail="No spec in progress")
        return builder

    @router.get("/graph-data", response_class=JSONResponse)
    async def get_graph_data() -> JSONResponse:
        """Get entity data for graph refresh."""
        builder = get_builder_state()
        if builder.spec is None:
            return JSONResponse({"entities": {}, "root_entity": None})

        entities_data = {}
        for name, entity in builder.spec.entities.items():
            entities_data[name] = {
                "ontology_term": entity.ontology_term,
                "description": entity.description or "",
                "fields": [
                    {
                        "name": f.name,
                        "type": f.type.value if hasattr(f.type, "value") else str(f.type),
                        "required": f.required,
                        "items": f.items,
                        "reference": f.reference,
                    }
                    for f in entity.fields
                ],
            }

        return JSONResponse(
            {
                "entities": entities_data,
                "root_entity": builder.spec.root_entity,
            }
        )

    @router.get("/preview", response_class=HTMLResponse)
    async def preview_yaml(request: Request) -> HTMLResponse:
        """Get YAML preview of the current spec."""
        builder = _require_spec()
        yaml_content = spec_to_yaml(builder.spec)

        return templates.TemplateResponse(
            request,
            "spec_builder/partials/yaml_preview.html",
            {"yaml_content": yaml_content},
        )

    @router.get("/export")
    async def export_yaml(_request: Request) -> StreamingResponse:
        """Download the spec as a YAML file."""
        builder = _require_spec()
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
        builder = _require_spec()

        # Apply any included metadata from the form
        form_data = await request.form()
        if form_data.get("name"):
            builder.spec.name = form_data.get("name", "").strip()
        if form_data.get("version"):
            builder.spec.version = form_data.get("version", "").strip()
        if form_data.get("display_name"):
            builder.spec.display_name = form_data.get("display_name", "").strip()
        if form_data.get("description"):
            builder.spec.description = form_data.get("description", "").strip()
        if form_data.get("root_entity"):
            builder.spec.root_entity = form_data.get("root_entity", "").strip()
        if form_data.get("ontology"):
            builder.spec.ontology = form_data.get("ontology", "").strip()

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

    @router.delete("/user-spec/{name}/{version}", response_class=HTMLResponse)
    async def delete_user_spec_route(_request: Request, name: str, version: str) -> Response:
        """Delete a user-created specification."""
        try:
            deleted = delete_user_spec(name, version)
            if deleted:
                return Response(status_code=200)
            raise HTTPException(status_code=404, detail=f"Spec {name} v{version} not found")
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
