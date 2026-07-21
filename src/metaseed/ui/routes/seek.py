"""Routes for pushing a profile's schema into a FAIRDOM-SEEK instance.

Only mounted behaviourally when the ``seek`` adapter is enabled on the Plugins
page: both handlers 404 when ``app.state.settings.adapter_enabled('seek')`` is
false, so disabling the plugin hides the feature.
"""

from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from metaseed.ui.spec_provider import SpecProvider
from metaseed.ui.state import AppState


def register_seek_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    _get_state: Callable[[], AppState],
    spec_provider: SpecProvider | None = None,
    base_url: str = "",
) -> None:
    """Register the "Push profile to SEEK" page and its submit endpoint."""
    if spec_provider is None:
        from metaseed.ui.spec_filesystem import FilesystemSpecProvider

        spec_provider = FilesystemSpecProvider()
    provider = spec_provider

    def _enabled(request: Request) -> bool:
        settings = request.app.state.settings
        enabled: bool = settings.adapter_enabled("seek")
        return enabled

    async def _profile_choices() -> list[dict[str, str]]:
        choices: list[dict[str, str]] = []
        for name in await provider.list_profiles():
            display = await provider.get_display_name(name)
            for version in await provider.list_versions(profile=name):
                choices.append(
                    {"value": f"{name}/{version}", "label": f"{display} ({version})"}
                )
        return choices

    @app.get("/seek", response_class=HTMLResponse)
    async def seek_page(request: Request) -> HTMLResponse:
        """Render the push-to-SEEK form (404 when the plugin is disabled)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)
        return templates.TemplateResponse(
            request,
            "seek/index.html",
            {"profiles": await _profile_choices(), "base_url": base_url},
        )

    @app.post("/seek/push", response_class=HTMLResponse)
    async def seek_push(request: Request) -> HTMLResponse:
        """Load the chosen profile and push its schema into the SEEK instance."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)

        form = await request.form()
        profile_spec = str(form.get("profile", ""))
        seek_url = str(form.get("seek_url", "")).strip()
        api_key = str(form.get("api_key", "")).strip()

        if "/" not in profile_spec or not seek_url or not api_key:
            return templates.TemplateResponse(
                request,
                "partials/seek_push_result.html",
                {"error": "Pick a profile and provide a SEEK URL and API key.",
                 "base_url": base_url},
                status_code=400,
            )

        name, version = profile_spec.split("/", 1)
        from metaseed.seek import SeekClient, push_profile
        from metaseed.specs.loader import SpecLoader, SpecLoadError

        try:
            profile = SpecLoader().load_profile(version, name)
            client = SeekClient(seek_url, token=api_key)
            result = push_profile(client, profile)
        except (SpecLoadError, ValueError, OSError) as exc:
            return templates.TemplateResponse(
                request,
                "partials/seek_push_result.html",
                {"error": str(exc), "base_url": base_url},
                status_code=502,
            )
        except Exception as exc:  # surface any client/HTTP error to the user
            return templates.TemplateResponse(
                request,
                "partials/seek_push_result.html",
                {"error": f"{type(exc).__name__}: {exc}", "base_url": base_url},
                status_code=502,
            )

        return templates.TemplateResponse(
            request,
            "partials/seek_push_result.html",
            {
                "result": result,
                "seek_url": seek_url,
                "profile_spec": profile_spec,
                "base_url": base_url,
            },
        )

    @app.get("/seek/extended-metadata")
    async def seek_extended_metadata(request: Request, profile: str = "") -> Response:
        """Download the Extended Metadata Type JSON for a profile (admin uploads it)."""
        if not _enabled(request):
            return HTMLResponse("SEEK plugin is disabled", status_code=404)
        if "/" not in profile:
            return HTMLResponse("Provide ?profile=name/version", status_code=400)

        name, version = profile.split("/", 1)
        from metaseed.seek.config import extended_metadata_json
        from metaseed.specs.loader import SpecLoader, SpecLoadError

        try:
            spec = SpecLoader().load_profile(version, name)
        except (SpecLoadError, ValueError, OSError) as exc:
            return HTMLResponse(str(exc), status_code=404)

        blocks = [
            block
            for entity_name in spec.entities
            if (block := extended_metadata_json(spec, entity_name)) is not None
        ]
        return JSONResponse(
            blocks,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{name}-{version}-extended-metadata.json"'
                )
            },
        )
