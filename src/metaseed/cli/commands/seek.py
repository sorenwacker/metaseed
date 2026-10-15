"""`metaseed seek` — provisioning a FAIRDOM-SEEK instance and pushing to it.

Wrappers over :mod:`metaseed.seek`, the same functions the SEEK page calls, so
a sync from a terminal creates exactly what a sync from the browser creates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, load_profile_spec, open_dataset
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
    from metaseed.seek.preview import build_model_preview

    spec = load_profile_spec(profile, version)
    model = build_model_preview(spec)
    emit(
        {
            "profile": spec.name,
            "version": spec.version,
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
    from metaseed.seek.provision import (
        build_provisioning_plan,
        execute_provisioning_plan,
    )

    spec = load_profile_spec(profile, version)
    client = _client()
    target = (
        project_id
        or Settings().get_adapter_config("seek").get("project_id")
        or client.default_project_id()
    )
    plan = build_provisioning_plan(spec)
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

    metaseed_client, data = open_dataset(dataset)
    client = _client()
    target = (
        project_id
        or Settings().get_adapter_config("seek").get("project_id")
        or client.default_project_id()
    )
    profile = load_profile_spec(data.profile, data.version)
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
    from metaseed.seek.templates import to_isa_template_json

    payload = to_isa_template_json(load_profile_spec(profile, version))
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
    from metaseed.seek.fairds import to_fair_data_station_model_rdf

    text = to_fair_data_station_model_rdf(load_profile_spec(profile, version))
    if output is None:
        typer.echo(text)
        return
    output.write_text(text)
    echo_success(f"Wrote {output}.")


@app.command(name="import-templates")
def seek_import_templates(
    profile: Annotated[Path, typer.Argument(help="Profile YAML to update")],
    templates: Annotated[
        list[Path], typer.Argument(help="SEEK ISA Template JSON files")
    ],
    write: Annotated[
        bool, typer.Option("--write", help="Rewrite the profile (default: report)")
    ] = False,
) -> None:
    """Re-derive a profile's template-bound entities from SEEK template files.

    Every entity whose ``seek.template`` names one of the templates gets that
    template's attributes as its fields, column for column: attribute type,
    required flag, title attribute, ISA tag and vocabulary. What only the
    profile knows (an Input field's reference, ontology terms, identity
    markers) is kept. The file is the source of truth SEEK's API does not
    expose once a template is installed.
    """
    import json

    from metaseed.seek.definitions import apply_isa_templates

    document = yaml.safe_load(profile.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    for path in templates:
        entries.extend(json.loads(path.read_text(encoding="utf-8"))["data"])
    applied = apply_isa_templates(document, entries)
    if not applied:
        echo_error("no entity of the profile names one of these templates")
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    for entity_name, dropped in applied.items():
        note = f" (dropped: {', '.join(dropped)})" if dropped else ""
        typer.echo(f"{entity_name}: re-derived from its template{note}")
    if write:
        profile.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8",
        )
        echo_success(f"wrote {profile}")
    else:
        typer.echo("DRY RUN - use --write to rewrite the profile")
