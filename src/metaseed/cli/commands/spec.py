"""`metaseed spec` — authoring a profile from the command line.

The web interface and the MCP server hold a draft in a session; a command line
has none, so a draft here is a YAML file that each command reads, changes
through :class:`~metaseed.specs.builder.SpecBuilder` — the same builder both
other surfaces use — and writes back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, parse_assignments

app = typer.Typer(
    name="spec", no_args_is_help=True, help="Author a profile specification."
)

DRAFT = Annotated[Path, typer.Argument(help="The draft YAML file")]
SET_HELP = "Attribute as name=value; repeatable."


def _open(draft: Path) -> Any:
    """The draft as a builder, or exit saying it is not there."""
    from metaseed.specs.builder import SpecBuilder

    if not draft.exists():
        echo_error(f"No draft at {draft}. `metaseed spec create {draft}` starts one.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    try:
        return SpecBuilder.from_yaml(draft.read_text())
    except Exception as exc:
        echo_error(f"{draft} is not a readable specification: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc


def _write(builder: Any, draft: Path, message: str) -> None:
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(builder.to_yaml())
    echo_success(message)


def _changing(draft: Path, message: str, change: Any) -> None:
    """Apply one builder change to a draft, reporting a refusal as one."""
    builder = _open(draft)
    try:
        change(builder)
    except (ValueError, KeyError) as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    _write(builder, draft, message)


@app.command("create")
def create(
    draft: DRAFT,
    name: Annotated[str, typer.Option("--name", "-n", help="Profile name")],
    version: Annotated[str, typer.Option("--version", "-v")] = "1.0",
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
) -> None:
    """Start a new draft."""
    from metaseed.specs.builder import SpecBuilder

    builder = SpecBuilder.empty(
        name=name,
        version=version,
        display_name=display_name or name,
        description=description or "",
    )
    _write(builder, draft, f"Started {name} {version} at {draft}.")


@app.command("clone")
def clone(
    draft: DRAFT,
    profile: Annotated[str, typer.Argument(help="Profile to copy")],
    version: Annotated[str, typer.Argument(help="Its version")],
) -> None:
    """Start a draft from an existing profile."""
    from metaseed.specs.builder import SpecBuilder

    try:
        builder = SpecBuilder.from_template(profile, version)
    except Exception as exc:
        echo_error(f"Could not clone {profile} {version}: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    _write(builder, draft, f"Cloned {profile} {version} into {draft}.")


@app.command("import")
def import_yaml(
    draft: DRAFT,
    source: Annotated[Path, typer.Argument(help="A specification YAML document")],
) -> None:
    """Start a draft from a specification document written elsewhere."""
    from metaseed.specs.builder import SpecBuilder

    if not source.exists():
        echo_error(f"No such file: {source}")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    try:
        builder = SpecBuilder.from_yaml(source.read_text())
    except Exception as exc:
        echo_error(f"{source} is not a readable specification: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    _write(builder, draft, f"Imported {source} into {draft}.")


@app.command("status")
def status(draft: DRAFT) -> None:
    """Name, version, root entity, entity and rule counts."""
    spec = _open(draft).spec
    emit(
        {
            "name": spec.name,
            "version": spec.version,
            "display_name": spec.display_name,
            "root_entity": spec.root_entity,
            "entities": {
                name: len(entity.fields) for name, entity in spec.entities.items()
            },
            "validation_rules": [rule.name for rule in spec.validation_rules],
        }
    )


@app.command("preview")
def preview(draft: DRAFT) -> None:
    """Print the draft as the profile YAML it would become."""
    typer.echo(_open(draft).to_yaml())


@app.command("validate")
def validate(draft: DRAFT) -> None:
    """Report what is wrong with the draft, and what merely looks unintended."""
    builder = _open(draft)
    problems = builder.validate()
    emit({"valid": not problems, "problems": problems, "warnings": builder.warnings()})
    if problems:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("save")
def save(
    draft: DRAFT,
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Save under another name")
    ] = None,
) -> None:
    """Save the draft as a profile in the user specs directory."""
    from metaseed.specs.persistence import save_spec

    builder = _open(draft)
    problems = builder.validate()
    if problems:
        echo_error("The draft does not build: " + "; ".join(problems))
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    path = save_spec(builder.spec, name)
    echo_success(f"Saved {builder.spec.name} {builder.spec.version} to {path}.")


@app.command("delete")
def delete(
    name: Annotated[str, typer.Argument(help="Profile name")],
    version: Annotated[
        str | None, typer.Argument(help="Version; all if omitted")
    ] = None,
) -> None:
    """Remove a profile from the user specs directory."""
    from metaseed.specs.persistence import delete_user_spec

    if not delete_user_spec(name, version):
        echo_error(f"No user profile {name} {version or ''}".rstrip() + ".")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    echo_success(f"Deleted {name} {version or '(all versions)'}.")


@app.command("set-metadata")
def set_metadata(
    draft: DRAFT,
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Change profile-level fields: name, version, display_name, description, ontology."""
    fields = parse_assignments(set_)
    _changing(
        draft,
        f"Updated {', '.join(fields) or 'nothing'}.",
        lambda b: b.set_metadata(**fields),
    )


@app.command("set-root")
def set_root(
    draft: DRAFT, entity: Annotated[str, typer.Argument(help="Entity type")]
) -> None:
    """Set the entity a dataset starts from."""
    _changing(
        draft, f"Root entity is now {entity}.", lambda b: b.set_root_entity(entity)
    )


@app.command("add-entity")
def add_entity(
    draft: DRAFT,
    name: Annotated[str, typer.Argument(help="Entity type name")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Add an entity type."""
    attrs = parse_assignments(set_)
    _changing(draft, f"Added entity {name}.", lambda b: b.add_entity(name, **attrs))


@app.command("update-entity")
def update_entity(
    draft: DRAFT,
    name: Annotated[str, typer.Argument(help="Entity type name")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Change an entity's description or ontology term."""
    attrs = parse_assignments(set_)
    _changing(
        draft, f"Updated entity {name}.", lambda b: b.update_entity(name, **attrs)
    )


@app.command("rename-entity")
def rename_entity(
    draft: DRAFT,
    old: Annotated[str, typer.Argument(help="Current name")],
    new: Annotated[str, typer.Argument(help="New name")],
) -> None:
    """Rename an entity type, following every reference to it."""
    _changing(draft, f"Renamed {old} to {new}.", lambda b: b.rename_entity(old, new))


@app.command("delete-entity")
def delete_entity(
    draft: DRAFT, name: Annotated[str, typer.Argument(help="Entity type")]
) -> None:
    """Remove an entity type."""
    _changing(draft, f"Removed entity {name}.", lambda b: b.delete_entity(name))


@app.command("add-field")
def add_field(
    draft: DRAFT,
    entity: Annotated[str, typer.Argument(help="Entity type")],
    name: Annotated[str, typer.Argument(help="Field name")],
    field_type: Annotated[str, typer.Option("--type", "-t")] = "string",
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Add a field to an entity.

    ``--set items=Child`` on a ``list`` or ``entity`` field is what nests one
    entity type under another, which is how a dataset ever reaches the child.
    """
    attrs = parse_assignments(set_)
    _changing(
        draft,
        f"Added {entity}.{name}.",
        lambda b: b.add_field(entity, name, field_type, **attrs),
    )


@app.command("update-field")
def update_field(
    draft: DRAFT,
    entity: Annotated[str, typer.Argument(help="Entity type")],
    name: Annotated[str, typer.Argument(help="Field name")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Change a field's attributes; unnamed ones keep their values."""
    attrs = parse_assignments(set_)
    _changing(
        draft,
        f"Updated {entity}.{name}.",
        lambda b: b.update_field(entity, name, **attrs),
    )


@app.command("delete-field")
def delete_field(
    draft: DRAFT,
    entity: Annotated[str, typer.Argument(help="Entity type")],
    name: Annotated[str, typer.Argument(help="Field name")],
) -> None:
    """Remove a field."""
    _changing(
        draft, f"Removed {entity}.{name}.", lambda b: b.delete_field(entity, name)
    )


@app.command("move-field")
def move_field(
    draft: DRAFT,
    entity: Annotated[str, typer.Argument(help="Entity type")],
    name: Annotated[str, typer.Argument(help="Field name")],
    direction: Annotated[str, typer.Argument(help="up or down")],
) -> None:
    """Move a field one position up or down."""
    if direction not in ("up", "down"):
        echo_error("Direction is 'up' or 'down'.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    _changing(
        draft,
        f"Moved {entity}.{name} {direction}.",
        lambda b: b.move_field(entity, name, direction),
    )


@app.command("add-rule")
def add_rule(
    draft: DRAFT,
    name: Annotated[str, typer.Argument(help="Rule name")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Add a validation rule."""
    attrs = parse_assignments(set_)
    _changing(draft, f"Added rule {name}.", lambda b: b.add_rule(name, **attrs))


@app.command("update-rule")
def update_rule(
    draft: DRAFT,
    name: Annotated[str, typer.Argument(help="Rule name")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Change a validation rule."""
    attrs = parse_assignments(set_)
    _changing(draft, f"Updated rule {name}.", lambda b: b.update_rule(name, **attrs))


@app.command("delete-rule")
def delete_rule(
    draft: DRAFT, name: Annotated[str, typer.Argument(help="Rule name")]
) -> None:
    """Remove a validation rule."""
    _changing(draft, f"Removed rule {name}.", lambda b: b.delete_rule(name))


@app.command("notes")
def notes(
    draft: DRAFT,
    text: Annotated[str | None, typer.Argument(help="Note text; omit to read")] = None,
) -> None:
    """Read or set the draft's notes.

    Notes live beside the draft in ``<draft>.notes``: they are the author's
    working comments, not part of the profile the specification produces.
    """
    path = draft.with_suffix(draft.suffix + ".notes")
    if text is None:
        typer.echo(path.read_text() if path.exists() else "")
        return
    path.write_text(text)
    echo_success(f"Wrote notes to {path}.")
