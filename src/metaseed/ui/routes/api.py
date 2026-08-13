"""API routes for data retrieval.

Provides JSON API endpoints for lookups, graph data, and spec operations.
Includes WebSocket endpoint for real-time updates.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from fastapi import Body, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from metaseed.specs.loader import SpecLoadError
from metaseed.specs.merge import compare, merge

from ..dataset_manager import resolve_dataset_manager
from ..helpers import collect_entities_by_type, get_reference_fields
from ..websocket import manager

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState, TreeNode


def _parse_profile_strings(
    profiles: list[str],
) -> tuple[list[tuple[str, str]], str | None]:
    """Parse profile strings into tuples.

    Args:
        profiles: List of profile identifiers (e.g., ["miappe/1.1", "isa/1.0"]).

    Returns:
        Tuple of (profile_tuples, error_message). Error is None if parsing succeeded.
    """
    profile_tuples = []
    for p in profiles:
        parts = p.split("/")
        if len(parts) != 2:
            return [], f"Invalid profile format: {p}. Use profile/version"
        profile_tuples.append((parts[0], parts[1]))
    return profile_tuples, None


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

        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/compare")
    async def compare_profiles(
        profiles: list[str] = Body(..., description="List of profile/version strings"),
    ) -> JSONResponse:
        """Compare multiple profile specifications.

        Args:
            profiles: List of profile identifiers (e.g., ["miappe/1.1", "isa/1.0"]).

        Returns:
            JSON with comparison results including statistics and entity diffs.
        """
        if len(profiles) < 1:
            return JSONResponse(
                status_code=400,
                content={"error": "At least 1 profile required"},
            )

        try:
            profile_tuples, error = _parse_profile_strings(profiles)
            if error:
                return JSONResponse(status_code=400, content={"error": error})

            result = compare(profile_tuples)

            # Convert to JSON-serializable format
            entity_diffs = []
            for ed in result.entity_diffs:
                field_diffs = []
                for fd in ed.field_diffs:
                    field_diffs.append(
                        {
                            "field_name": fd.field_name,
                            "diff_type": fd.diff_type.value,
                            "profiles": {
                                pid: spec.model_dump() if spec else None
                                for pid, spec in fd.profiles.items()
                            },
                            "attributes_changed": fd.attributes_changed,
                            "is_conflict": fd.is_conflict,
                        }
                    )

                entity_diffs.append(
                    {
                        "entity_name": ed.entity_name,
                        "diff_type": ed.diff_type.value,
                        "profiles": ed.profiles,
                        "field_diffs": field_diffs,
                        "has_conflicts": ed.has_conflicts,
                    }
                )

            return JSONResponse(
                content={
                    "profiles": result.profiles,
                    "statistics": {
                        "total_entities": result.statistics.total_entities,
                        "common_entities": result.statistics.common_entities,
                        "unique_entities": result.statistics.unique_entities,
                        "modified_entities": result.statistics.modified_entities,
                        "total_fields": result.statistics.total_fields,
                        "common_fields": result.statistics.common_fields,
                        "modified_fields": result.statistics.modified_fields,
                        "conflicting_fields": result.statistics.conflicting_fields,
                    },
                    "entity_diffs": entity_diffs,
                }
            )

        except (ValueError, SpecLoadError) as e:
            return JSONResponse(
                status_code=500,
                content={"error": str(e)},
            )

    @app.post("/api/merge")
    async def merge_profiles(
        profiles: list[str] = Body(..., description="List of profile/version strings"),
        strategy: str = Body(default="first_wins", description="Merge strategy"),
        output_name: str = Body(
            default="merged", description="Name for merged profile"
        ),
        output_version: str = Body(
            default="1.0", description="Version for merged profile"
        ),
    ) -> JSONResponse:
        """Merge multiple profile specifications into one.

        Args:
            profiles: List of profile identifiers (e.g., ["miappe/1.1", "isa/1.0"]).
            strategy: Merge strategy (first_wins, last_wins, most_restrictive,
                     least_restrictive, prefer_<profile>).
            output_name: Name for the merged profile.
            output_version: Version string for merged profile.

        Returns:
            JSON with merged profile spec and merge metadata.
        """
        if len(profiles) < 2:
            return JSONResponse(
                status_code=400,
                content={"error": "At least 2 profiles required for merge"},
            )

        try:
            profile_tuples, error = _parse_profile_strings(profiles)
            if error:
                return JSONResponse(status_code=400, content={"error": error})

            result = merge(
                profiles=profile_tuples,
                strategy=strategy,
                output_name=output_name,
                output_version=output_version,
            )

            # Convert warnings to JSON
            warnings = [
                {"entity": w.entity_name, "field": w.field_name, "message": w.message}
                for w in result.warnings
            ]

            # Convert unresolved conflicts
            unresolved = [
                {
                    "entity": c.entity_name if hasattr(c, "entity_name") else "",
                    "field": c.field_name,
                    "diff_type": c.diff_type.value,
                }
                for c in result.unresolved_conflicts
            ]

            return JSONResponse(
                content={
                    "merged_profile": result.to_dict(),
                    "yaml": result.to_yaml(),
                    "strategy_used": strategy,
                    "source_profiles": profiles,
                    "warnings": warnings,
                    "has_unresolved_conflicts": result.has_unresolved_conflicts,
                    "unresolved_conflicts": unresolved,
                    "resolutions_applied": len(result.resolutions_applied),
                }
            )

        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={"error": str(e)},
            )
        except SpecLoadError as e:
            return JSONResponse(
                status_code=500,
                content={"error": str(e)},
            )

    # =========================================================================
    # MCP Server Status (MCP is mounted in-process, always running)
    # =========================================================================

    @app.get("/api/mcp/status")
    async def mcp_status() -> JSONResponse:
        """Get MCP server status.

        Returns:
            JSON with running status and connection URL.
        """
        from metaseed.agent.mcp.manager import get_mcp_manager

        manager = get_mcp_manager()
        status = manager.status()

        return JSONResponse(
            content={
                "running": status.running,
                "transport": status.transport,
                "host": status.host,
                "port": status.port,
                "pid": status.pid,
                "url": manager.get_connection_url() if status.running else None,
                "error": status.error,
            }
        )

    @app.post("/api/mcp/start")
    async def mcp_start() -> JSONResponse:
        """Start MCP server on port 8001.

        Returns:
            JSON with status.
        """
        from metaseed.agent.mcp.manager import get_mcp_manager

        manager = get_mcp_manager()
        status = manager.start()

        return JSONResponse(
            content={
                "running": status.running,
                "transport": status.transport,
                "host": status.host,
                "port": status.port,
                "pid": status.pid,
                "url": manager.get_connection_url() if status.running else None,
                "error": status.error,
            }
        )

    @app.post("/api/mcp/stop")
    async def mcp_stop() -> JSONResponse:
        """Stop MCP server.

        Returns:
            JSON with status.
        """
        from metaseed.agent.mcp.manager import get_mcp_manager

        manager = get_mcp_manager()
        status = manager.stop()

        return JSONResponse(
            content={
                "running": status.running,
                "error": status.error,
            }
        )

    # =========================================================================
    # Dataset Management
    # =========================================================================

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
        return JSONResponse(
            content={
                "results": [hit.to_dict() for hit in hits],
                "not_asked": source.not_interactive(),
            }
        )
