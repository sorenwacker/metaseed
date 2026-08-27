"""API routes for data retrieval.

Provides JSON API endpoints for lookups, graph data, and spec operations.
Includes WebSocket endpoint for real-time updates.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from fastapi import Body, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ..dataset_manager import resolve_dataset_manager
from ..helpers import collect_entities_by_type, get_reference_fields
from ..websocket import manager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState, TreeNode


def register_api_routes(  # noqa: C901
    app: FastAPI,
    get_state: Callable[[], AppState],
) -> None:
    """Register API routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        get_state: Callable returning AppState.
    """

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time updates.

        Clients connect here to receive notifications when state changes
        (e.g., entities created/updated via MCP).
        """
        await manager.connect(websocket)
        try:
            while True:
                # Keep connection alive, wait for messages (we don't expect any)
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(websocket)

    @app.get("/api/lookup/{entity_type}")
    async def lookup_entities(
        entity_type: str,
        q: str = Query(default="", description="Search query"),
    ) -> JSONResponse:
        """Search entities of a given type for autocomplete.

        Args:
            entity_type: The type of entity to search (e.g., "ObservationUnit").
            q: Search query to filter by identifier and label fields.

        Returns:
            JSON with results list containing value and label for each match.
        """
        state = get_state()
        facade = state.get_or_create_facade()

        entities_by_type = collect_entities_by_type(state, facade)
        entities = entities_by_type.get(entity_type, [])

        query = q.lower().strip()
        if query:
            filtered = []
            for entity in entities:
                value = entity.get("value", "").lower()
                label = entity.get("label", "").lower()
                if query in value or query in label:
                    filtered.append(entity)
            entities = filtered

        seen = set()
        results = []
        for entity in entities:
            value = entity.get("value", "")
            if value and value not in seen:
                seen.add(value)
                results.append(
                    {
                        "value": value,
                        "label": entity.get("label", value),
                    }
                )

        return JSONResponse(content={"results": results})

    @app.get("/api/reference-fields/{entity_type}")
    async def get_reference_fields_api(entity_type: str) -> JSONResponse:
        """Get reference field definitions for an entity type.

        Args:
            entity_type: The entity type to get reference fields for.

        Returns:
            JSON with reference fields mapping field name to target info.
        """
        state = get_state()
        facade = state.get_or_create_facade()

        ref_fields = get_reference_fields(
            profile=state.profile,
            version=facade.version,
            entity_type=entity_type,
        )

        return JSONResponse(content=ref_fields)

    @app.get("/api/graph")
    async def get_graph() -> JSONResponse:
        """Return graph data for visualization.

        Reloads current dataset from disk to pick up MCP changes,
        then builds nodes and edges for vis.js network graph.

        Returns:
            JSON with 'nodes' and 'edges' lists.
        """
        from metaseed.ui.datasets import get_current_dataset_name
        from metaseed.ui.services.graph import build_graph

        state = get_state()
        manager = resolve_dataset_manager(app, state)

        # Reload from disk to pick up MCP changes
        current_dataset = get_current_dataset_name(state) or manager.current_dataset
        if current_dataset:
            with contextlib.suppress(FileNotFoundError):
                manager.load_dataset(current_dataset)

        return JSONResponse(content=build_graph(state))

    @app.get("/api/validate")
    async def validate_dataset_api() -> JSONResponse:
        """Validate all entities in the current dataset recursively.

        Returns:
            JSON with validation summary and per-entity results.
        """
        from metaseed.ui.datasets import get_current_dataset_name
        from metaseed.validators import validate_entity

        state = get_state()
        manager = resolve_dataset_manager(app, state)

        # Reload from disk to pick up MCP changes
        current_dataset = get_current_dataset_name(state) or manager.current_dataset
        if current_dataset:
            with contextlib.suppress(FileNotFoundError):
                manager.load_dataset(current_dataset)

        try:
            facade = state.get_or_create_facade()
            results = []

            def validate_recursive(node: TreeNode) -> None:
                errors = []
                if node.instance:
                    data = node.instance.model_dump(exclude_none=True)
                    validation_errors = validate_entity(
                        data=data,
                        entity_type=node.entity_type,
                        profile=facade.profile,
                        version=facade.version,
                    )
                    for err in validation_errors:
                        errors.append(
                            {
                                "field": err.field,
                                "message": err.message,
                            }
                        )

                results.append(
                    {
                        "id": node.id,
                        "entity_type": node.entity_type,
                        "label": node.label,
                        "valid": len(errors) == 0,
                        "errors": errors,
                    }
                )

                for child in node.children:
                    validate_recursive(child)

            for node in state.entity_tree:
                validate_recursive(node)

            return JSONResponse(
                content={
                    "dataset": current_dataset,
                    "total": len(results),
                    "valid": sum(1 for r in results if r["valid"]),
                    "invalid": sum(1 for r in results if not r["valid"]),
                    "results": results,
                }
            )

        except Exception:
            # The cause goes to the log; the client gets that it failed, not
            # the exception's text, which can name paths and internals.
            logger.exception("Graph could not be built")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "The graph could not be built. The server log has the cause."
                },
            )

    @app.get("/api/datasets")
    async def list_datasets_api() -> JSONResponse:
        """List all saved datasets.

        Returns:
            JSON array of dataset info.
        """
        from dataclasses import asdict

        state = get_state()
        manager = resolve_dataset_manager(app, state)
        datasets = [asdict(d) for d in manager.list_datasets()]

        return JSONResponse(
            content={
                "datasets": datasets,
                "current": manager.current_dataset,
            }
        )

    @app.post("/api/datasets/save")
    async def save_dataset_api(
        name: str = Body(..., embed=True, description="Dataset name"),
    ) -> JSONResponse:
        """Save current state as a dataset.

        Args:
            name: Dataset name (alphanumeric, hyphens, underscores).

        Returns:
            JSON with saved dataset info or error.
        """
        from dataclasses import asdict

        state = get_state()
        manager = resolve_dataset_manager(app, state)

        try:
            result = manager.save_dataset(name)
            return JSONResponse(content={"status": "saved", **asdict(result)})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    @app.post("/api/datasets/load")
    async def load_dataset_api(
        name: str = Body(..., embed=True, description="Dataset name"),
    ) -> JSONResponse:
        """Load a dataset.

        Args:
            name: Dataset name to load.

        Returns:
            JSON with loaded dataset info or error.
        """
        from dataclasses import asdict

        state = get_state()
        manager = resolve_dataset_manager(app, state)

        try:
            result = manager.load_dataset(name)
            # Sync current dataset name to state for MCP auto-save
            from ..datasets import set_current_dataset_name

            set_current_dataset_name(state, name)
            return JSONResponse(content={"status": "loaded", **asdict(result)})
        except FileNotFoundError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    @app.delete("/api/datasets/{name}")
    async def delete_dataset_api(name: str) -> JSONResponse:
        """Delete a dataset.

        Args:
            name: Dataset name to delete.

        Returns:
            JSON with status.
        """
        state = get_state()
        manager = resolve_dataset_manager(app, state)

        if manager.delete_dataset(name):
            return JSONResponse(content={"status": "deleted"})
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    # =========================================================================
    # Ontology Lookup
    # =========================================================================

    @app.get("/api/ontology/search")
    async def search_ontology_terms(
        q: str = Query(default="", description="Search query"),
        ontology: str | None = Query(
            default=None,
            description="Ontology ID(s) to filter, comma-separated (e.g., 'po,pato')",
        ),
        within: str | None = Query(
            default=None,
            description="Restrict to terms beneath this one (e.g. 'JERM:00025')",
        ),
    ) -> JSONResponse:
        """Search the configured term sources for matching terms.

        Local vocabularies are asked before OLS, so a term that exists only in
        a project's own list is offered in the picker rather than being
        unfindable — which was the case while this route spoke to OLS4 alone.

        Args:
            q: Search query to find matching ontology terms.
            ontology: Optional ontology ID(s) to restrict search.
                Supports comma-separated values (e.g., "po,pato").
            within: Optional ontology term whose descendants are the valid
                values, so a column takes one branch rather than a whole
                ontology (#229).

        Returns:
            JSON with results list containing value, label, description,
            ontology and the source that answered, plus ``not_asked`` naming
            any source left out for being too slow to type against.
        """
        from metaseed.services.terms import get_term_source

        if not q.strip():
            return JSONResponse(content={"results": [], "not_asked": []})

        source = get_term_source()
        # A person is waiting at a keyboard for this: it backs the term picker.
        # A source that has declared it cannot answer at that speed is left out
        # rather than allowed to stall the dialog — plan07 measured OLS taking
        # 51 seconds for PO — and is named in the response, because a shorter
        # list of results is indistinguishable from there being less to find
        # (#247).
        hits = await source.search(q, ontology, 20, within, interactive=True)
        # Both ways a source is left out are named: declared too slow for a
        # picker, and unable to honour the branch restriction — no local
        # vocabulary implements `within`, so a branch-scoped search skipped
        # every local source with nothing to say so.
        not_asked = sorted({*source.not_interactive(), *source.cannot_restrict(within)})
        return JSONResponse(
            content={
                "results": [hit.to_dict() for hit in hits],
                "not_asked": not_asked,
            }
        )
