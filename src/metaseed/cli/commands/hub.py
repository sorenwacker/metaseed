"""`metaseed hub` — pushing to and pulling from a metaseed-hub.

Thin wrappers over :mod:`metaseed.hub.sync` and :mod:`metaseed.hub.profiles`,
the same functions the web interface calls, so a push from a terminal and a
push from the browser behave identically: a plan before anything is sent, and
nothing overwritten without being asked for.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success, echo_warning
from metaseed.cli.workspace import emit, load_data, repository
from metaseed.settings import Settings

app = typer.Typer(
    name="hub", no_args_is_help=True, help="Push to and pull from a metaseed-hub."
)


def client() -> Any:
    """The configured hub client, or exit saying what is missing."""
    from metaseed.hub import client_from_settings

    config = Settings().get_adapter_config("hub")
    try:
        return client_from_settings(config)
    except ValueError as exc:
        echo_error(
            f"{exc} (Settings -> Plugins -> Metaseed Hub, or `metaseed plugin config hub`.)"
        )
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc


def _fail(exc: Exception, hub: Any) -> None:
    from metaseed.hub.connection import describe_failure

    echo_error(describe_failure(exc, hub.url))
    raise typer.Exit(ExitCode.INPUT_ERROR) from exc


@app.command("check")
def check() -> None:
    """Say which hub account and tenant the stored token acts in."""
    from metaseed.hub.connection import check_connection

    outcome = check_connection(Settings().get_adapter_config("hub"))
    typer.echo(outcome.message)
    if not outcome.ok:
        raise typer.Exit(ExitCode.CONFIG_ERROR)


@app.command("list")
def list_datasets() -> None:
    """List your datasets on the hub, and where a pull would land."""
    from metaseed.hub.sync import (
        dataset_pull_target,
        list_hub_datasets,
        local_counterpart,
    )

    hub = client()
    try:
        records = list_hub_datasets(hub)
    except Exception as exc:
        _fail(exc, hub)
        return
    store = repository()
    rows = []
    for record in records:
        target = dataset_pull_target(record, local_counterpart(store, record.name))
        rows.append(
            {
                "id": record.id,
                "name": record.name,
                "profile": record.profile,
                "version": record.version,
                "entities": record.entity_count,
                "pull_would": target.kind,
                "pull_as": target.name,
            }
        )
    emit(rows)


@app.command("push-dataset")
def push_dataset(
    name: Annotated[str, typer.Argument(help="Local dataset name")],
    replace: Annotated[
        bool, typer.Option("--replace", help="Replace a differing hub dataset")
    ] = False,
    plan_only: Annotated[
        bool, typer.Option("--plan", help="Show what would happen, send nothing")
    ] = False,
) -> None:
    """Push a dataset to the hub.

    Without ``--replace`` a hub dataset of the same name that differs is left
    alone and the difference is printed.
    """
    from metaseed.hub.sync import find_remote_by_name, plan_dataset_push, provenance
    from metaseed.hub.sync import push_dataset as push

    hub = client()
    local = load_data(name)
    if plan_only:
        try:
            plan = plan_dataset_push(local, find_remote_by_name(hub, name))
        except Exception as exc:
            _fail(exc, hub)
            return
        emit(
            {
                "dataset": name,
                "hub": hub.url,
                "would": plan.kind,
                "added": plan.added,
                "changed": plan.changed,
                "removed": plan.removed,
                "counts": {t: list(pair) for t, pair in plan.counts.items()},
            }
        )
        return
    try:
        outcome = push(hub, local, replace=replace)
    except Exception as exc:
        _fail(exc, hub)
        return
    if outcome.provenance is not None:
        local.hub = outcome.provenance
        repository().save(name, local)
    if outcome.kind == "differs":
        echo_warning(
            f"'{name}' differs on {hub.url} and was not sent: "
            f"{len(outcome.plan.added)} to add, {len(outcome.plan.changed)} to change, "
            f"{len(outcome.plan.removed)} to remove. Pass --replace to send it anyway."
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    messages = {
        "create": f"Created '{name}' on {hub.url}.",
        "replaced": f"Replaced '{name}' on {hub.url}.",
        "identical": f"'{name}' on {hub.url} is identical; nothing was sent.",
    }
    echo_success(messages[outcome.kind])
    if outcome.provenance is None:
        return
    _ = provenance  # the stamp came from the push; named here for the reader


@app.command("pull-dataset")
def pull_dataset(
    dataset_id: Annotated[str, typer.Argument(help="Hub dataset id, from `hub list`")],
) -> None:
    """Pull one hub dataset.

    A local dataset of the same name that differs is never overwritten: the
    copy lands beside it as ``<name>-hub``.
    """
    from metaseed.hub.sync import (
        HubRecord,
        dataset_pull_target,
        local_counterpart,
        provenance,
    )

    hub = client()
    try:
        record = HubRecord.from_row(hub.get_dataset(dataset_id))
    except Exception as exc:
        _fail(exc, hub)
        return
    store = repository()
    target = dataset_pull_target(record, local_counterpart(store, record.name))
    if target.kind == "identical":
        echo_success(f"'{record.name}' is already here, unchanged.")
        return
    data = record.as_dataset(target.name)
    data.hub = provenance(hub, direction="pull")
    store.save(target.name, data)
    beside = " (the differing local one was kept)" if target.kind == "beside" else ""
    echo_success(f"Pulled '{record.name}' as '{target.name}'{beside}.")


@app.command("profiles")
def profiles() -> None:
    """List your local profiles and the hub's published ones."""
    from metaseed.hub.profiles import (
        ProfileRef,
        local_hash,
        local_profiles,
        profile_pull_target,
    )

    hub = client()
    try:
        published = hub.list_specs()
    except Exception as exc:
        _fail(exc, hub)
        return
    specs_dir = _specs_dir()
    # Your own entry per name and version: a publication outranks a draft.
    by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    for s in published:
        if not s.get("mine", False):
            continue
        key = (s["name"], s["version"])
        if key not in by_ref or s.get("visibility") == "published":
            by_ref[key] = s
    emit(
        {
            "local": [
                {
                    "name": ref.name,
                    "version": ref.version,
                    "on_hub": _held_state(
                        by_ref.get((ref.name, ref.version)), local_hash(specs_dir, ref)
                    ),
                }
                for ref in local_profiles(specs_dir)
            ],
            # What the hub holds: your drafts and every published
            # specification, each saying which it is.
            "on_hub": [
                {
                    "name": s["name"],
                    "version": s["version"],
                    "visibility": s.get("visibility", "published"),
                    "mine": bool(s.get("mine", False)),
                    "here": profile_pull_target(
                        specs_dir,
                        ProfileRef(s["name"], s["version"]),
                        s.get("content_hash"),
                    ).kind,
                }
                for s in published
            ],
        }
    )


def _held_state(held: dict[str, Any] | None, digest: str | None) -> str:
    """What your account holds for a local profile: draft, published, or nothing."""
    if held is None:
        return "not on the hub"
    same = held.get("content_hash") == digest
    kind = held.get("visibility", "published")
    return f"{kind}{'' if same else ', different content'}"


def _specs_dir() -> Any:
    from metaseed.paths import get_user_specs_dir

    return get_user_specs_dir()


@app.command("push-profile")
def push_profile(
    name: Annotated[str, typer.Argument(help="Profile name")],
    version: Annotated[str, typer.Argument(help="Profile version")],
    publish: Annotated[
        bool,
        typer.Option(
            "--publish", help="Publish for every hub user, not just as your draft"
        ),
    ] = False,
) -> None:
    """Push one of your profiles to the hub, as a private draft unless --publish."""
    from metaseed.hub.client import HubApiError
    from metaseed.hub.profiles import ProfileRef
    from metaseed.hub.profiles import push_profile as push

    hub = client()
    try:
        outcome = push(hub, _specs_dir(), ProfileRef(name, version), publish=publish)
    except FileNotFoundError as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    except HubApiError as exc:
        echo_error(f"The hub refused it: {exc.detail}")
        raise typer.Exit(ExitCode.VALIDATION_ERROR) from exc
    except Exception as exc:
        _fail(exc, hub)
        return
    messages = {
        "draft": f"Pushed {name} {version} to {hub.url} as your private draft",
        "published": f"Published {name} {version} on {hub.url} for every hub user",
        "identical": f"{name} {version} is already published on {hub.url}, unchanged",
    }
    echo_success(
        f"{messages[outcome.kind]} (content hash {outcome.content_hash[:12]})."
    )


@app.command("unpublish-profile")
def unpublish_profile(
    name: Annotated[str, typer.Argument(help="Profile name")],
    version: Annotated[str, typer.Argument(help="Profile version")],
) -> None:
    """Withdraw a profile you published back to a private draft."""
    from metaseed.hub.client import HubApiError
    from metaseed.hub.profiles import ProfileRef
    from metaseed.hub.profiles import unpublish_profile as withdraw

    hub = client()
    try:
        withdrawn = withdraw(hub, ProfileRef(name, version))
    except HubApiError as exc:
        echo_error(f"The hub refused it: {exc.detail}")
        raise typer.Exit(ExitCode.VALIDATION_ERROR) from exc
    except Exception as exc:
        _fail(exc, hub)
        return
    if not withdrawn:
        echo_error(f"{name} {version} is not published from your account on {hub.url}.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    echo_success(
        f"Withdrew {name} {version} on {hub.url}; it is your private draft again."
    )


@app.command("pull-profile")
def pull_profile(
    name: Annotated[str, typer.Argument(help="Profile name")],
    version: Annotated[str, typer.Argument(help="Profile version")],
) -> None:
    """Fetch a published profile into your specs directory.

    A local profile of that name and version is never replaced.
    """
    from metaseed.hub.profiles import ProfileRef
    from metaseed.hub.profiles import pull_profile as pull

    hub = client()
    try:
        target = pull(hub, _specs_dir(), ProfileRef(name, version))
    except Exception as exc:
        _fail(exc, hub)
        return
    if target.kind == "new":
        echo_success(f"Pulled {name} {version}.")
        return
    if target.kind == "identical":
        echo_success(f"{name} {version} is already here, unchanged.")
        return
    echo_error(
        f"{name} {version} exists here with different content and was not replaced. "
        "Remove or rename the local one to pull the hub's."
    )
    raise typer.Exit(ExitCode.VALIDATION_ERROR)
