"""`metaseed seek` — provisioning a FAIRDOM-SEEK instance and pushing to it.

Wrappers over :mod:`metaseed.seek`, the same functions the SEEK page calls, so
a sync from a terminal creates exactly what a sync from the browser creates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, open_dataset
from metaseed.settings import Settings

app = typer.Typer(name="seek", no_args_is_help=True, help="FAIRDOM-SEEK.")


def _client() -> Any:
    """The configured SEEK client, or exit saying what is missing."""
    from metaseed.seek import client_from_settings

    try:
        return client_from_settings(Settings().get_adapter_config("seek"))
    except ValueError as exc:
        echo_error(
            f"{exc} (`metaseed plugin config seek --set url=... --set api_key=...`)"
        )
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc


def _profile_of(dataset: str) -> Any:
    from metaseed.specs.loader import SpecLoader

    _client_obj, data = open_dataset(dataset)
    return SpecLoader().load_profile(version=data.version, profile=data.profile)


@app.command("check")
def check() -> None:
    """Say whether the stored URL and key reach a SEEK instance."""
    from metaseed.seek.connection import check_connection

    outcome = check_connection(Settings().get_adapter_config("seek"))
    typer.echo(outcome.message)
    for identifier, title in outcome.projects:
        typer.echo(f"  {identifier}  {title}")
    if not outcome.ok:
        raise typer.Exit(ExitCode.CONFIG_ERROR)


@app.command("preview")
def preview(
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
) -> None:
    """Show the SEEK model a profile would create, without touching an instance."""
    from metaseed.cli.app import resolve_profile_version
    from metaseed.seek.preview import build_model_preview
    from metaseed.specs.loader import SpecLoader

    name, resolved = resolve_profile_version(profile, version)
    model = build_model_preview(
        SpecLoader().load_profile(version=resolved, profile=name)
    )
    emit(
        {
            "profile": name,
            "version": resolved,
            "sample_types": [
                {
                    "title": sample_type.title,
                    "template": getattr(sample_type, "template", None),
                    "level": getattr(sample_type, "level", None),
                    "attributes": [a.name for a in sample_type.attributes],
                }
                for sample_type in model.sample_types
            ],
        }
    )


@app.command("provision")
def provision(
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
    project_id: Annotated[
        str | None, typer.Option("--project", help="SEEK project id")
    ] = None,
) -> None:
    """Create the Sample Types and controlled vocabularies a profile needs."""
    from metaseed.cli.app import resolve_profile_version
    from metaseed.seek.provision import (
        build_provisioning_plan,
        execute_provisioning_plan,
    )
    from metaseed.specs.loader import SpecLoader

    name, resolved = resolve_profile_version(profile, version)
    client = _client()
    target = (
        project_id
        or Settings().get_adapter_config("seek").get("project_id")
        or client.default_project_id()
    )
    plan = build_provisioning_plan(
        SpecLoader().load_profile(version=resolved, profile=name)
    )
    try:
        result = execute_provisioning_plan(client, plan, project_id=str(target))
    except Exception as exc:
        echo_error(f"Provisioning failed: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    emit(
        {
            "project": target,
            "vocabularies": result.cv_ids,
            "sample_types": result.sample_type_ids,
            "created": result.created,
            "reused": result.reused,
            "errors": result.errors,
        }
    )
    if result.errors:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("sync")
def sync(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    project_id: Annotated[
        str | None, typer.Option("--project", help="SEEK project id")
    ] = None,
) -> None:
    """Push a dataset into SEEK as Investigations, Studies, Assays and Samples."""
    from metaseed.seek.provision import resolve_cv_ids
    from metaseed.seek.sync import sync_dataset_to_seek
    from metaseed.specs.loader import SpecLoader

    metaseed_client, data = open_dataset(dataset)
    client = _client()
    target = (
        project_id
        or Settings().get_adapter_config("seek").get("project_id")
        or client.default_project_id()
    )
    profile = SpecLoader().load_profile(version=data.version, profile=data.profile)
    try:
        result = sync_dataset_to_seek(
            client,
            metaseed_client,
            project_id=str(target),
            cv_ids=resolve_cv_ids(client, profile),
        )
    except Exception as exc:
        echo_error(f"Sync failed: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    emit(
        {
            "project": target,
            "investigations": result.investigations,
            "studies": result.studies,
            "assays": result.assays,
            "samples": len(result.samples),
            "data_files": len(result.data_files),
            "reused": len(result.reused),
            "skipped": result.skipped,
            "unlinked": result.unlinked,
            "notes": result.notes,
            "errors": result.errors,
        }
    )
    if result.errors:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("isa-rdf")
def isa_rdf(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Write a dataset as FAIR Data Station ISA RDF."""
    from metaseed.seek.fairds import to_fair_data_station_rdf

    client, _data = open_dataset(dataset)
    text = to_fair_data_station_rdf(client)
    if output is None:
        typer.echo(text)
        return
    output.write_text(text)
    echo_success(f"Wrote {output}.")


@app.command("isa-templates")
def isa_templates(
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Write a profile as SEEK ISA Template JSON, ready to populate an instance."""
    from metaseed.cli.app import resolve_profile_version
    from metaseed.seek.templates import to_isa_template_json
    from metaseed.specs.loader import SpecLoader

    name, resolved = resolve_profile_version(profile, version)
    payload = to_isa_template_json(
        SpecLoader().load_profile(version=resolved, profile=name)
    )
    text = json.dumps(payload, indent=2)
    if output is None:
        typer.echo(text)
        return
    output.write_text(text)
    echo_success(f"Wrote {output}.")


@app.command("model-ttl")
def model_ttl(
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Write a profile as the FAIR Data Station model, in Turtle."""
    from metaseed.cli.app import resolve_profile_version
    from metaseed.seek.fairds import to_fair_data_station_model_rdf
    from metaseed.specs.loader import SpecLoader

    name, resolved = resolve_profile_version(profile, version)
    text = to_fair_data_station_model_rdf(
        SpecLoader().load_profile(version=resolved, profile=name)
    )
    if output is None:
        typer.echo(text)
        return
    output.write_text(text)
    echo_success(f"Wrote {output}.")
