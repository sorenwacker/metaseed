"""`metaseed dataset` — the saved datasets on this machine.

Each command names the dataset it acts on; there is no session to load into.
The work is done by the same objects the web interface and the MCP tools use:
:class:`~metaseed.repositories.filesystem_dataset.FilesystemDatasetRepository`
for storage and :class:`~metaseed.api.client.MetaseedClient` for the entities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, load_data, open_dataset, repository
from metaseed.repositories.dataset_repository import DatasetData

app = typer.Typer(name="dataset", no_args_is_help=True, help="Saved datasets.")


@app.command("list")
def list_datasets() -> None:
    """List the saved datasets, newest first."""
    emit(
        [
            {
                "name": info.name,
                "profile": info.profile,
                "version": info.version,
                "entities": info.entity_count,
                "created": info.created,
                "modified": info.modified,
                "hub": info.hub,
            }
            for info in repository().list()
        ]
    )


@app.command("show")
def show_dataset(
    name: Annotated[str, typer.Argument(help="Dataset name")],
    tree: Annotated[bool, typer.Option("--tree", help="As a nested tree")] = False,
) -> None:
    """Print a dataset's entities."""
    client, data = open_dataset(name)
    emit(
        {
            "name": data.name,
            "profile": data.profile,
            "version": data.version,
            "created": data.created,
            "modified": data.modified,
            "hub": data.hub,
            **client.serialize(format="tree" if tree else "flat"),
        }
    )


@app.command("create")
def create_dataset(
    name: Annotated[str, typer.Argument(help="Dataset name")],
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
) -> None:
    """Create an empty dataset bound to a profile version."""
    from metaseed.cli.app import resolve_profile_version

    profile_name, profile_version = resolve_profile_version(profile, version)
    if repository().exists(name):
        echo_error(f"A dataset named '{name}' already exists.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    try:
        info = repository().save(
            name, DatasetData(name=name, profile=profile_name, version=profile_version)
        )
    except ValueError as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    echo_success(f"Created '{info.name}' ({info.profile} {info.version}).")


@app.command("delete")
def delete_dataset(name: Annotated[str, typer.Argument(help="Dataset name")]) -> None:
    """Delete a saved dataset."""
    if not repository().delete(name):
        echo_error(f"No dataset named '{name}'.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    echo_success(f"Deleted '{name}'.")


@app.command("import")
def import_dataset(
    name: Annotated[str, typer.Argument(help="Dataset name to write")],
    source: Annotated[Path, typer.Argument(help="JSON or YAML file of entities")],
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
) -> None:
    """Write the entities of a JSON or YAML file into a dataset.

    The file may be a whole saved dataset (with ``profile`` and ``version``) or
    a bare list of entities, in which case the profile has to be named.
    """
    import yaml

    if not source.exists():
        echo_error(f"No such file: {source}")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    try:
        payload: Any = yaml.safe_load(source.read_text())
    except yaml.YAMLError as exc:
        echo_error(f"{source} is not readable as JSON or YAML: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    entities = payload.get("entities") if isinstance(payload, dict) else payload
    if not isinstance(entities, list):
        echo_error(f"{source} holds no list of entities.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    stored = isinstance(payload, dict) and payload.get("profile")
    profile_name = profile or (payload.get("profile") if stored else None)
    profile_version = version or (payload.get("version") if stored else None)
    if not profile_name:
        echo_error("The file does not name a profile; pass --profile and --version.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    data = DatasetData(
        name=name,
        profile=str(profile_name),
        version=str(profile_version or ""),
        entities=entities,
    )
    try:
        info = repository().save(name, data)
    except ValueError as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    echo_success(f"Wrote {info.entity_count} entities into '{name}'.")


@app.command("import-record")
def import_record(
    name: Annotated[str, typer.Argument(help="Dataset name to write")],
    accession: Annotated[str, typer.Argument(help="Accession or URL of the record")],
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
) -> None:
    """Fetch a public record through an import adapter and save it.

    The adapter is chosen by profile, from the same registry the web interface
    and the MCP server use, so all three import the same way.
    """
    from metaseed.adapters import import_action_for_profile, importable_profiles
    from metaseed.cli.app import resolve_profile_version

    profile_name, profile_version = resolve_profile_version(profile, version)
    action = import_action_for_profile(profile_name)
    if action is None:
        echo_error(
            f"No import adapter for profile '{profile_name}'. "
            f"Profiles that can import: {', '.join(sorted(importable_profiles())) or 'none'}."
        )
        raise typer.Exit(ExitCode.CONFIG_ERROR)
    try:
        payload = action.resolve()(accession)
    except Exception as exc:
        echo_error(f"{action.label} failed for '{accession}': {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    entities = (
        payload.get("entities", payload) if isinstance(payload, dict) else payload
    )
    data = DatasetData(
        name=name,
        profile=str(
            (payload.get("profile") if isinstance(payload, dict) else None)
            or profile_name
        ),
        version=str(
            (payload.get("version") if isinstance(payload, dict) else None)
            or profile_version
        ),
        entities=list(entities or []),
    )
    info = repository().save(name, data)
    echo_success(f"Imported {accession} into '{name}' ({info.entity_count} entities).")


@app.command("validate")
def validate_dataset(name: Annotated[str, typer.Argument(help="Dataset name")]) -> None:
    """Validate every entity of a dataset against its profile."""
    client, _data = open_dataset(name)
    result = client.validate()
    emit(
        {
            "dataset": name,
            "valid": result.valid,
            "issues": [
                {
                    "entity_id": issue.entity_id,
                    "field": issue.field,
                    "message": issue.message,
                    "rule": issue.rule,
                    "kind": issue.kind,
                }
                for issue in result.issues
            ],
        }
    )
    if not result.valid:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("validate-links")
def validate_links(name: Annotated[str, typer.Argument(help="Dataset name")]) -> None:
    """Report entities that are not linked to a parent or a reference.

    The same check the ``validate_relationships`` MCP tool reports: an entity
    the profile expects to hang off another, standing on its own.
    """
    from metaseed.specs.loader import SpecLoader

    client, data = open_dataset(name)
    spec = SpecLoader().load_profile(version=data.version, profile=data.profile)
    unlinked = [
        {
            "id": node.id,
            "type": node.entity_type,
            "label": client.get_entity_label(node.id),
        }
        for node in client.get_roots()
        if node.entity_type != spec.root_entity
    ]
    emit({"dataset": name, "linked": not unlinked, "unlinked": unlinked})
    if unlinked:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("export")
def export_dataset(
    name: Annotated[str, typer.Argument(help="Dataset name")],
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="json, yaml, or an adapter key")
    ] = "json",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Write a dataset out as JSON, YAML, or through an export adapter.

    `metaseed plugin list` shows which adapter formats are installed.
    """
    import yaml

    from metaseed.adapters import actions_for_profile, find_action

    client, data = open_dataset(name)
    if fmt in ("json", "yaml"):
        payload = {
            "profile": data.profile,
            "version": data.version,
            **client.serialize(),
        }
        text = (
            json.dumps(payload, indent=2, default=str)
            if fmt == "json"
            else yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        )
        files = {f"{name}.{fmt}": text}
    else:
        action = find_action(fmt)
        offered = [a.key for a in actions_for_profile(data.profile, kind="export")]
        if action is None or fmt not in offered:
            echo_error(
                f"'{fmt}' is not an export this profile offers. "
                f"Available: {', '.join(['json', 'yaml', *sorted(offered)])}."
            )
            raise typer.Exit(ExitCode.INPUT_ERROR)
        try:
            files = action.resolve()(client)
        except Exception as exc:
            echo_error(f"{action.label} failed: {exc}")
            raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    if output is None:
        for content in files.values():
            typer.echo(content if isinstance(content, str) else content.decode())
        return
    directory = output if len(files) > 1 else output.parent
    directory.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        path = output if len(files) == 1 else directory / filename
        path.write_bytes(content.encode() if isinstance(content, str) else content)
    echo_success(f"Wrote {', '.join(sorted(files))} to {output}.")


@app.command("info")
def dataset_info(name: Annotated[str, typer.Argument(help="Dataset name")]) -> None:
    """Profile, version and entity counts of a dataset."""
    data = load_data(name)
    counts: dict[str, int] = {}
    for entity in data.entities:
        entity_type = str(entity.get("_type", "?"))
        counts[entity_type] = counts.get(entity_type, 0) + 1
    emit(
        {
            "name": data.name,
            "profile": data.profile,
            "version": data.version,
            "entities": len(data.entities),
            "by_type": dict(sorted(counts.items())),
            "hub": data.hub,
        }
    )
