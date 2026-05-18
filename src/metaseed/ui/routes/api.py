"""API routes for data retrieval.

Provides JSON API endpoints for lookups, graph data, and spec operations.
Includes WebSocket endpoint for real-time updates.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from fastapi import Body, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from metaseed.specs.loader import SpecLoadError
from metaseed.specs.merge import compare, merge

from ..helpers import collect_entities_by_type, get_reference_fields
from ..websocket import manager

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState


def _parse_profile_strings(profiles: list[str]) -> tuple[list[tuple[str, str]], str | None]:
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


def register_api_routes(
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
        from metaseed.ui.datasets import get_current_dataset_name, load_dataset
        from metaseed.ui.services.graph import build_graph

        state = get_state()

        # Reload from disk to pick up MCP changes
        current_dataset = get_current_dataset_name(state)
        if current_dataset:
            with contextlib.suppress(FileNotFoundError):
                load_dataset(state, current_dataset)

        return JSONResponse(content=build_graph(state))

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
        output_name: str = Body(default="merged", description="Name for merged profile"),
        output_version: str = Body(default="1.0", description="Version for merged profile"),
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
    async def mcp_status(request: Request) -> JSONResponse:
        """Get MCP server status.

        MCP is mounted in-process at /mcp, always running with shared state.

        Returns:
            JSON with running status and connection URL.
        """
        # Build URL from request
        host = request.headers.get("host", "127.0.0.1:8765")
        scheme = request.headers.get("x-forwarded-proto", "http")
        url = f"{scheme}://{host}/mcp"

        return JSONResponse(
            content={
                "running": True,
                "transport": "in-process",
                "host": host.split(":")[0],
                "port": int(host.split(":")[1]) if ":" in host else 80,
                "pid": None,
                "url": url,
                "error": None,
            }
        )

    @app.post("/api/mcp/start")
    async def mcp_start() -> JSONResponse:
        """Start MCP server (no-op, always running in-process).

        Returns:
            JSON with status.
        """
        return JSONResponse(
            content={
                "running": True,
                "transport": "in-process",
                "message": "MCP is always running (mounted in-process at /mcp)",
                "error": None,
            }
        )

    @app.post("/api/mcp/stop")
    async def mcp_stop() -> JSONResponse:
        """Stop MCP server (no-op, always running in-process).

        Returns:
            JSON with status.
        """
        return JSONResponse(
            content={
                "running": True,
                "message": "MCP cannot be stopped (mounted in-process)",
                "error": None,
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
        from ..datasets import get_current_dataset_name, list_datasets

        state = get_state()
        datasets = list_datasets()
        current = get_current_dataset_name(state)

        return JSONResponse(
            content={
                "datasets": datasets,
                "current": current,
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
        from ..datasets import save_dataset, set_current_dataset_name

        state = get_state()

        try:
            result = save_dataset(state, name)
            set_current_dataset_name(state, name)
            return JSONResponse(content={"status": "saved", **result})
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
        from ..datasets import load_dataset, set_current_dataset_name

        state = get_state()

        try:
            result = load_dataset(state, name)
            set_current_dataset_name(state, name)
            return JSONResponse(content={"status": "loaded", **result})
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
        from ..datasets import delete_dataset, get_current_dataset_name, set_current_dataset_name

        state = get_state()

        if delete_dataset(name):
            # Clear current if it was the deleted one
            if get_current_dataset_name(state) == name:
                set_current_dataset_name(state, None)
            return JSONResponse(content={"status": "deleted"})
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})
