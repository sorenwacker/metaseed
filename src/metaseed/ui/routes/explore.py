"""Routes for profile exploration and comparison functionality."""

from collections.abc import Callable, Sequence

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from metaseed.specs.loader import SpecLoadError
from metaseed.specs.merge import (
    CSVReportGenerator,
    DiffVisualizer,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    compare,
)
from metaseed.ui.routes.hub import hub_configured
from metaseed.ui.spec_provider import SpecProvider
from metaseed.ui.state import AppState


def _parse_profile_specs(
    specs: Sequence[object],
) -> tuple[list[tuple[str, str]], str | None]:
    """Parse "name/version" strings, naming the first malformed one.

    Silently dropping a spec without a "/" let a fully malformed selection
    reach compare([]) and surface as a 500; the malformed entry is the
    caller's mistake and must be named in a 400.
    """
    tuples: list[tuple[str, str]] = []
    for spec in specs:
        if not isinstance(spec, str) or "/" not in spec:
            return [], f"Malformed profile spec: {spec!r} (expected name/version)"
        name, version = spec.split("/", 1)
        tuples.append((name, version))
    return tuples, None


def register_explore_routes(  # noqa: C901
    app: FastAPI,
    templates: Jinja2Templates,
    _get_state: Callable[[], AppState],
    spec_provider: SpecProvider | None = None,
    base_url: str = "",
) -> None:
    """Register explore-related routes.

    Args:
        app: FastAPI application instance.
        templates: Jinja2 templates instance.
        _get_state: Function to get app state (unused, kept for API consistency).
        spec_provider: Optional spec provider for accessing specifications.
            If not provided, uses FilesystemSpecProvider.
        base_url: Base URL prefix for the application (e.g., "/hub").
            Should not have a trailing slash. Defaults to empty string.
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
                "base_url": base_url,
                "hub_enabled": hub_configured(request.app.state.settings),
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

        profile_tuples, parse_error = _parse_profile_specs(list(profile_specs))
        if parse_error:
            return JSONResponse({"error": parse_error}, status_code=400)

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

        except (ValueError, SpecLoadError) as e:
            # Same contract as /api/merge: user-selected profiles that fail
            # to load are the caller's mistake.
            return JSONResponse({"error": str(e)}, status_code=400)

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

        profile_tuples, parse_error = _parse_profile_specs(profile_specs)
        if parse_error:
            return JSONResponse({"error": parse_error}, status_code=400)

        try:
            result = compare(profile_tuples)
            visualizer = DiffVisualizer()
            graph_data = visualizer.build_diff_graph(result)

            return JSONResponse(graph_data)

        except (ValueError, SpecLoadError) as e:
            # The caller named the profiles; a profile that does not exist is
            # their mistake, not a server failure — same contract as /api/merge.
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.get("/explore/report/{format_type}/{profiles:path}")
    async def get_report(format_type: str, profiles: str) -> Response:
        """Get comparison report in specified format.

        Args:
            format_type: Report format (markdown, csv, html).
            profiles: Comma-separated profile specs.
        """
        profile_specs = profiles.split(",")

        profile_tuples, parse_error = _parse_profile_specs(profile_specs)
        if parse_error:
            # The message quotes what the caller sent; as text it cannot be
            # rendered as markup.
            return PlainTextResponse(content=f"Error: {parse_error}", status_code=400)

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

        except (ValueError, SpecLoadError) as e:
            return PlainTextResponse(content=f"Error: {e}", status_code=400)
