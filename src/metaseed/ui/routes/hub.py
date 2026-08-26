"""Push and pull against a metaseed-hub, from the datasets overview and the explorer.

Every route renders a partial into the page's hub panel. A push is shown as a
plan first and sent only on the second request; a pull never writes over a
differing local dataset or profile (see ``docs/guides/hub-sync.md``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from metaseed.ui.dataset_manager import resolve_dataset_manager
from metaseed.ui.state import AppState


def hub_client_from_settings(config: dict[str, str]) -> Any:
    """Build the hub client from the stored adapter config.

    A module-level seam so route tests can substitute a fake hub.
    """
    from metaseed.hub import client_from_settings

    return client_from_settings(config)


def hub_configured(settings: Any) -> bool:
    """Whether the hub adapter is enabled and points at a hub.

    The adapter is enabled by default when httpx is installed, so "enabled"
    alone would put hub buttons on every page; they appear once a URL and a
    token are set.
    """
    if not settings.adapter_enabled("hub"):
        return False
    config = settings.get_adapter_config("hub")
    return bool(
        (config.get("url") or "").strip() and (config.get("token") or "").strip()
    )


def user_specs_dir() -> Path:
    """Where user-local profiles live (a seam for tests)."""
    from metaseed.paths import get_user_specs_dir

    return get_user_specs_dir()


def register_hub_routes(  # noqa: C901
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
    base_url: str = "",
) -> None:
    """Register the hub push/pull routes."""

    def _status(request: Request, **context: Any) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "hub/status.html", {"base_url": base_url, **context}
        )

    def _hub(request: Request) -> tuple[Any, str | None]:
        """The hub client, or the reason there is none."""
        settings = request.app.state.settings
        if not hub_configured(settings):
            return None, (
                "Set the hub URL and access token under Settings → Plugins first "
                "(Metaseed Hub)."
            )
        try:
            return hub_client_from_settings(settings.get_adapter_config("hub")), None
        except ModuleNotFoundError:
            return None, "Hub access needs httpx: pip install 'metaseed[hub]'."
        except ValueError as exc:
            return None, str(exc)

    def _failure(exc: Exception, hub: Any) -> str:
        from metaseed.hub.connection import describe_failure

        return describe_failure(exc, hub.url)

    @app.get("/hub/datasets/{name}/push", response_class=HTMLResponse)
    async def push_dataset_plan(request: Request, name: str) -> HTMLResponse:
        """What pushing ``name`` would do on the hub; nothing is sent."""
        from metaseed.hub.sync import find_remote_by_name, plan_dataset_push

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        manager = resolve_dataset_manager(app, get_state())
        try:
            local = manager.repository.load(name)
            plan = plan_dataset_push(local, find_remote_by_name(hub, name))
        except FileNotFoundError:
            return _status(request, error=f"No saved dataset named {name!r}.")
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        return templates.TemplateResponse(
            request,
            "hub/push_plan.html",
            {"base_url": base_url, "name": name, "plan": plan, "hub_url": hub.url},
        )

    @app.post("/hub/datasets/{name}/push", response_class=HTMLResponse)
    async def push_dataset_now(
        request: Request, name: str, replace: str = Form("")
    ) -> HTMLResponse:
        """Push ``name``; a differing hub dataset is replaced only with ``replace``."""
        from metaseed.hub.sync import push_dataset

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        manager = resolve_dataset_manager(app, get_state())
        try:
            local = manager.repository.load(name)
            outcome = push_dataset(hub, local, replace=replace == "1")
        except FileNotFoundError:
            return _status(request, error=f"No saved dataset named {name!r}.")
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        if outcome.provenance is not None:
            local.hub = outcome.provenance
            manager.repository.save(name, local)
        messages = {
            "create": f"Created {name!r} on {hub.url}.",
            "replaced": f"Replaced {name!r} on {hub.url}.",
            "identical": f"{name!r} on {hub.url} is identical; nothing was sent.",
            "differs": f"{name!r} differs on the hub; nothing was sent.",
        }
        return _status(
            request,
            ok=outcome.kind != "differs",
            message=messages[outcome.kind],
            plan=outcome.plan if outcome.kind == "differs" else None,
            name=name,
            refresh=outcome.provenance is not None,
        )

    @app.get("/hub/datasets/pull", response_class=HTMLResponse)
    async def pull_list(request: Request) -> HTMLResponse:
        """The caller's hub datasets, each with where a pull would land."""
        from metaseed.hub.sync import (
            dataset_pull_target,
            list_hub_datasets,
            local_counterpart,
        )

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        manager = resolve_dataset_manager(app, get_state())
        try:
            records = list_hub_datasets(hub)
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        rows = [
            (
                record,
                dataset_pull_target(
                    record, local_counterpart(manager.repository, record.name)
                ),
            )
            for record in records
        ]
        return templates.TemplateResponse(
            request,
            "hub/pull_list.html",
            {"base_url": base_url, "rows": rows, "hub_url": hub.url},
        )

    @app.post("/hub/datasets/pull/{dataset_id}", response_class=HTMLResponse)
    async def pull_dataset_now(request: Request, dataset_id: str) -> HTMLResponse:
        """Pull one hub dataset; a differing local one is kept and the copy lands beside it."""
        from metaseed.hub.sync import (
            HubRecord,
            dataset_pull_target,
            local_counterpart,
            provenance,
        )

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        manager = resolve_dataset_manager(app, get_state())
        try:
            record = HubRecord.from_row(hub.get_dataset(dataset_id))
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        target = dataset_pull_target(
            record, local_counterpart(manager.repository, record.name)
        )
        if target.kind == "identical":
            return _status(
                request, ok=True, message=f"{record.name!r} is already here, unchanged."
            )
        data = record.as_dataset(target.name)
        data.hub = provenance(hub, direction="pull")
        manager.repository.save(target.name, data)
        note = (
            f" A local {record.name!r} differs, so the copy is saved beside it."
            if target.kind == "beside"
            else ""
        )
        return _status(
            request,
            ok=True,
            message=f"Pulled {record.name!r} as {target.name!r}.{note}",
            refresh=True,
        )

    @app.get("/hub/profiles", response_class=HTMLResponse)
    async def profiles_panel(request: Request) -> HTMLResponse:
        """User-local profiles to push and hub specifications to pull."""
        from metaseed.hub.profiles import (
            ProfileRef,
            local_hash,
            local_profiles,
            profile_pull_target,
        )

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        try:
            published = hub.list_specs()
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        specs_dir = user_specs_dir()
        local: list[tuple[ProfileRef, str | None]] = []
        for ref in local_profiles(specs_dir):
            digest = local_hash(specs_dir, ref)
            on_hub = next(
                (
                    "identical" if s.get("content_hash") == digest else "differs"
                    for s in published
                    if (s["name"], s["version"]) == (ref.name, ref.version)
                ),
                None,
            )
            local.append((ref, on_hub))
        remote = [
            (
                s,
                profile_pull_target(
                    specs_dir,
                    ProfileRef(s["name"], s["version"]),
                    s.get("content_hash"),
                ),
            )
            for s in published
        ]
        return templates.TemplateResponse(
            request,
            "hub/profiles.html",
            {
                "base_url": base_url,
                "local": local,
                "remote": remote,
                "hub_url": hub.url,
            },
        )

    @app.post("/hub/profiles/{name}/{version}/push", response_class=HTMLResponse)
    async def push_profile_now(
        request: Request, name: str, version: str
    ) -> HTMLResponse:
        """Publish a user-local profile on the hub."""
        from metaseed.hub.client import HubApiError
        from metaseed.hub.profiles import ProfileRef, push_profile

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        try:
            outcome = push_profile(hub, user_specs_dir(), ProfileRef(name, version))
        except FileNotFoundError as exc:
            return _status(request, error=str(exc))
        except HubApiError as exc:
            return _status(request, error=f"The hub refused: {exc.detail}")
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        verb = "Published" if outcome.kind == "published" else "Already published"
        return _status(
            request,
            ok=True,
            message=f"{verb} {name} {version} on {hub.url} (content hash {outcome.content_hash[:12]}).",
        )

    @app.post("/hub/profiles/{name}/{version}/pull", response_class=HTMLResponse)
    async def pull_profile_now(
        request: Request, name: str, version: str
    ) -> HTMLResponse:
        """Save a hub specification as a user-local profile; never over a differing one."""
        from metaseed.hub.profiles import ProfileRef, pull_profile

        hub, error = _hub(request)
        if hub is None:
            return _status(request, error=error)
        try:
            target = pull_profile(hub, user_specs_dir(), ProfileRef(name, version))
        except Exception as exc:
            return _status(request, error=_failure(exc, hub))
        if target.kind == "new":
            return _status(
                request, ok=True, message=f"Pulled {name} {version}.", refresh=True
            )
        if target.kind == "identical":
            return _status(
                request,
                ok=True,
                message=f"{name} {version} is already here, unchanged.",
            )
        return _status(
            request,
            error=(
                f"{name} {version} exists here with different content and was not "
                "replaced. Remove or rename the local one to pull the hub's."
            ),
        )
