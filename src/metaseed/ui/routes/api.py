"""API routes for data retrieval.

Provides JSON API endpoints for lookups, graph data, and spec operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Body, Query
from fastapi.responses import JSONResponse

from metaseed.specs.merge import compare, merge

from ..helpers import collect_entities_by_type, get_reference_fields

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from ..state import AppState


def register_api_routes(
    app: FastAPI,
    get_state: Callable[[], AppState],
) -> None:
    """Register API routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        get_state: Callable returning AppState.
    """

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

        Builds nodes and edges from the entity tree for vis.js network graph.

        Returns:
            JSON with 'nodes' and 'edges' lists.
        """
        from metaseed.ui.services.graph import build_graph

        state = get_state()
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
            # Parse profile strings into tuples
            profile_tuples = []
            for p in profiles:
                parts = p.split("/")
                if len(parts) != 2:
                    return JSONResponse(
                        status_code=400,
                        content={"error": f"Invalid profile format: {p}. Use profile/version"},
                    )
                profile_tuples.append((parts[0], parts[1]))

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

        except Exception as e:
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
            # Parse profile strings into tuples
            profile_tuples = []
            for p in profiles:
                parts = p.split("/")
                if len(parts) != 2:
                    return JSONResponse(
                        status_code=400,
                        content={"error": f"Invalid profile format: {p}. Use profile/version"},
                    )
                profile_tuples.append((parts[0], parts[1]))

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
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": str(e)},
            )
