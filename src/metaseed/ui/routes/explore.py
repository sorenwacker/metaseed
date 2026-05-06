"""Routes for profile exploration and comparison functionality."""

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from metaseed.specs.merge import (
    CSVReportGenerator,
    DiffVisualizer,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    compare,
)
from metaseed.ui.spec_provider import SpecProvider
from metaseed.ui.state import AppState


def register_explore_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    _get_state: Callable[[], AppState],
    spec_provider: SpecProvider | None = None,
) -> None:
    """Register explore-related routes.

    Args:
        app: FastAPI application instance.
        templates: Jinja2 templates instance.
        _get_state: Function to get app state (unused, kept for API consistency).
        spec_provider: Optional spec provider for accessing specifications.
            If not provided, uses FilesystemSpecProvider.
    """
    # If no provider, use default filesystem implementation
    if spec_provider is None:
        from metaseed.ui.spec_filesystem import FilesystemSpecProvider

        spec_provider = FilesystemSpecProvider()

    @app.get("/explore/", response_class=HTMLResponse)
    async def explore_page(request: Request) -> HTMLResponse:
        """Render the explore comparison page."""
        profiles = await spec_provider.list_profiles()

        # Get versions and display names for each profile
        profile_versions = {}
        profile_display_names = {}
        for profile in profiles:
            versions = await spec_provider.list_versions(profile=profile)
            profile_versions[profile] = versions
            # Get display name from provider
            display_name = await spec_provider.get_display_name(profile)
            profile_display_names[profile] = display_name

        return templates.TemplateResponse(
            request,
            "explore/index.html",
            {
                "profiles": profiles,
                "profile_versions": profile_versions,
                "profile_display_names": profile_display_names,
            },
        )

    @app.post("/explore/compare")
    async def compare_profiles(request: Request) -> JSONResponse:
        """Compare selected profiles and return results."""
        form = await request.form()
        profile_specs = form.getlist("profiles")

        if len(profile_specs) < 1:
            return JSONResponse(
                {"error": "Select at least 1 profile"},
                status_code=400,
            )

        # Parse profile specs
        profile_tuples = []
        for spec in profile_specs:
            if "/" in spec:
                parts = spec.split("/", 1)
                profile_tuples.append((parts[0], parts[1]))

        try:
            result = compare(profile_tuples)

            # Generate visualization data
            visualizer = DiffVisualizer()
            graph_data = visualizer.build_diff_graph(result)

            # Generate report
            report = MarkdownReportGenerator(result).generate()

            return JSONResponse(
                {
                    "success": True,
                    "graph": graph_data,
                    "report": report,
                    "statistics": {
                        "profiles": result.profiles,
                        "total_entities": result.statistics.total_entities,
                        "common_entities": result.statistics.common_entities,
                        "unique_entities": result.statistics.unique_entities,
                        "modified_entities": result.statistics.modified_entities,
                        "total_fields": result.statistics.total_fields,
                        "common_fields": result.statistics.common_fields,
                        "conflicting_fields": result.statistics.conflicting_fields,
                    },
                }
            )

        except Exception as e:
            return JSONResponse(
                {"error": str(e)},
                status_code=500,
            )

    @app.get("/explore/graph/{profiles:path}")
    async def get_diff_graph(profiles: str) -> JSONResponse:
        """Get diff visualization data for profiles.

        Args:
            profiles: Comma-separated profile specs (e.g., "miappe/1.1,isa/1.0").
        """
        profile_specs = profiles.split(",")

        if len(profile_specs) < 1:
            return JSONResponse(
                {"error": "At least 1 profile required"},
                status_code=400,
            )

        profile_tuples = []
        for spec in profile_specs:
            if "/" in spec:
                parts = spec.split("/", 1)
                profile_tuples.append((parts[0], parts[1]))

        try:
            result = compare(profile_tuples)
            visualizer = DiffVisualizer()
            graph_data = visualizer.build_diff_graph(result)

            return JSONResponse(graph_data)

        except Exception as e:
            return JSONResponse(
                {"error": str(e)},
                status_code=500,
            )

    @app.get("/explore/report/{format_type}/{profiles:path}")
    async def get_report(format_type: str, profiles: str) -> HTMLResponse:
        """Get comparison report in specified format.

        Args:
            format_type: Report format (markdown, csv, html).
            profiles: Comma-separated profile specs.
        """
        profile_specs = profiles.split(",")

        profile_tuples = []
        for spec in profile_specs:
            if "/" in spec:
                parts = spec.split("/", 1)
                profile_tuples.append((parts[0], parts[1]))

        try:
            result = compare(profile_tuples)

            if format_type == "csv":
                content = CSVReportGenerator(result).generate()
                media_type = "text/csv"
            elif format_type == "html":
                content = HTMLReportGenerator(result).generate()
                media_type = "text/html"
            else:
                content = MarkdownReportGenerator(result).generate()
                media_type = "text/markdown"

            return HTMLResponse(content=content, media_type=media_type)

        except Exception as e:
            return HTMLResponse(
                content=f"Error: {e}",
                status_code=500,
            )
