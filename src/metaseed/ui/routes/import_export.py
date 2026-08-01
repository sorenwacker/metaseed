"""Import and export routes for data transfer.

Provides routes for exporting entity data to Excel and importing a dataset
from an uploaded JSON file.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

from fastapi import Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.requests import Request

from metaseed import adapters

from ..datasets import ImportSourceError, import_dataset, import_from_source
from ..services.export import export_to_bytes, generate_filename

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    from ..state import AppState


def export_options_for_profile(profile: str) -> list[dict[str, str]]:
    """Return ``[{key, label, surface}]`` adapter-export options for a profile.

    Derived from the adapter registry (:mod:`metaseed.adapters`) — the
    ``export``-kind actions — so a new exporter is offered in the UI by declaring
    it there, not by editing this route. ``surface`` lets the template group the
    buttons.
    """
    return [
        {"key": action.key, "label": action.label, "surface": action.surface}
        for action in adapters.actions_for_profile(profile, kind="export")
    ]


def import_options_for_profile(profile: str) -> list[dict[str, str]]:
    """Return ``[{key, label, input_label, input_placeholder}]`` for a profile.

    The counterpart of :func:`export_options_for_profile`: the ``import``-kind
    actions on the ``import-menu`` surface, so a new importer appears in the UI
    by declaring itself in :mod:`metaseed.adapters`. The wording travels with the
    action because what the field wants differs — an accession for the archives,
    a server URL for BrAPI — and the template must not hard-code either.
    """
    return [
        {
            "key": action.key,
            "label": action.label,
            "input_label": action.input_label,
            "input_placeholder": action.input_placeholder,
        }
        for action in adapters.actions_for_profile(
            profile, kind="import", surface="import-menu"
        )
    ]


def register_export_routes(
    app: FastAPI,
    templates: Jinja2Templates,  # noqa: ARG001
    get_state: Callable[[], AppState],
) -> None:
    """Register export routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance (unused, kept for API consistency).
        get_state: Callable returning AppState.
    """

    @app.get("/export")
    async def export_excel(_request: Request) -> StreamingResponse:
        """Export current entity data to Excel file."""
        state = get_state()

        output = export_to_bytes(state)
        filename = generate_filename(state)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/export/adapter/{fmt}")
    async def export_adapter(fmt: str, _request: Request) -> StreamingResponse:
        """Export the current dataset via an adapter, as a zip of its files."""
        action = adapters.find_action(fmt)
        if action is None or action.kind != "export":
            raise HTTPException(status_code=404, detail=f"Unknown export format: {fmt}")

        state = get_state()

        # Gate on the same predicate that decides which buttons are rendered.
        # Without this a hand-typed format runs an exporter against a profile it
        # was never meant for and returns a successful download of header-only
        # files (e.g. a darwin-core dataset exported as MetaboLights ISA-Tab).
        offered = adapters.actions_for_profile(state.profile, kind="export")
        if action not in offered:
            raise HTTPException(
                status_code=404,
                detail=f"{fmt} export is not available for the {state.profile} profile.",
            )

        from metaseed.api.client import MetaseedClient

        client = MetaseedClient.__new__(MetaseedClient)
        client._facade = state.get_or_create_facade()

        try:
            export_fn = action.resolve()
        except ModuleNotFoundError as exc:  # extra not installed
            raise HTTPException(
                status_code=400,
                detail=f"{fmt} export requires the matching metaseed extra.",
            ) from exc
        except (ImportError, AttributeError) as exc:
            # A broken transitive import or a stale ref: a plugin defect must
            # degrade to an error message, not an unhandled 500.
            raise HTTPException(
                status_code=500, detail=f"{fmt} export is misconfigured."
            ) from exc

        try:
            files: dict[str, str] = export_fn(client)
        except Exception as exc:  # any plugin failure degrades to an error page
            raise HTTPException(
                status_code=500, detail=f"{fmt} export failed: {exc}"
            ) from exc
        if not files:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Nothing to export for {fmt}: the dataset is empty or does "
                    f"not match this format's expected structure."
                ),
            )

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        buffer.seek(0)

        stem = generate_filename(state).rsplit(".", 1)[0] or "dataset"
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stem}-{fmt}.zip"'},
        )


def register_import_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
) -> None:
    """Register data import routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance for rendering notifications.
        get_state: Callable returning AppState.
    """

    @app.post("/import")
    async def import_json(request: Request, file: UploadFile) -> HTMLResponse:
        """Import an uploaded JSON dataset file into the current state."""
        state = get_state()
        raw = await file.read()
        try:
            info = import_dataset(state, raw)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "components/notification.html",
                {"type": "error", "message": f"Import failed: {exc}"},
            )

        return templates.TemplateResponse(
            request,
            "components/notification.html",
            {
                "type": "success",
                "message": (
                    f"Imported {info['entity_count']} entities "
                    f"from profile '{info['profile']}'"
                ),
            },
        )

    @app.post("/import/source")
    async def import_source(
        request: Request, key: str = Form(...), value: str = Form(...)
    ) -> HTMLResponse:
        """Import a public record from a source database by accession or URL."""
        state = get_state()

        action = adapters.find_action(key)
        if action is None:
            raise HTTPException(status_code=404, detail=f"Unknown importer: {key}")

        # Gate on the same predicate that renders the control. Ungated, a
        # hand-posted key would import a PRIDE project into a darwin-core
        # dataset and replace it with a foreign profile.
        offered = adapters.actions_for_profile(
            state.profile, kind="import", surface="import-menu"
        )
        if action not in offered:
            raise HTTPException(
                status_code=404,
                detail=f"{key} is not available for the {state.profile} profile.",
            )

        try:
            info = import_from_source(state, state.profile, value.strip())
        except ImportSourceError as exc:
            return _import_notification(request, templates, "error", str(exc))
        except ModuleNotFoundError:
            return _import_notification(
                request,
                templates,
                "error",
                f"{action.label} needs the matching metaseed extra installed.",
            )
        except Exception as exc:  # any adapter failure degrades to a message
            return _import_notification(
                request, templates, "error", f"Import failed: {exc}"
            )

        response = _import_notification(
            request,
            templates,
            "success",
            (
                f"Imported {info['entity_count']} entities "
                f"from {value.strip()} into profile '{info['profile']}'"
            ),
        )
        # The imported entities live outside the swapped fragment, so the page
        # has to reload; a notification alone would leave the user looking at
        # the empty dataset they just filled.
        response.headers["HX-Trigger"] = "refreshPage"
        return response


def _import_notification(
    request: Request,
    templates: Jinja2Templates,
    kind: str,
    message: str,
) -> HTMLResponse:
    """Render the shared notification partial for an import outcome."""
    response: HTMLResponse = templates.TemplateResponse(
        request,
        "components/notification.html",
        {"type": kind, "message": message},
    )
    return response
