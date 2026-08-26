"""`metaseed profile` — what a profile defines.

Read-only introspection, answering the same questions as the MCP server's
``get_profile_schema``, ``get_profile_relationships``, ``get_entity_fields``,
``get_required_fields`` and ``get_field_spec`` tools, from the same
:class:`~metaseed.specs.loader.SpecLoader`.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error
from metaseed.cli.workspace import emit

app = typer.Typer(name="profile", no_args_is_help=True, help="What a profile defines.")


def _spec(profile: str | None, version: str | None) -> Any:
    from metaseed.cli.app import resolve_profile_version
    from metaseed.specs.loader import SpecLoader

    name, resolved = resolve_profile_version(profile, version)
    try:
        return SpecLoader().load_profile(version=resolved, profile=name)
    except Exception as exc:
        echo_error(f"Could not load profile {name} {resolved}: {exc}")
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc


def _entity(spec: Any, entity_type: str) -> Any:
    entity = spec.entities.get(entity_type)
    if entity is None:
        echo_error(
            f"'{entity_type}' is not an entity of {spec.name} {spec.version}. "
            f"Available: {', '.join(sorted(spec.entities))}."
        )
        raise typer.Exit(ExitCode.INPUT_ERROR)
    return entity


def _field_summary(field: Any) -> dict[str, Any]:
    return {
        "name": field.name,
        "type": getattr(field.type, "value", str(field.type)),
        "required": field.required,
        "items": field.items,
        "description": field.description,
        "ontology_term": field.ontology_term,
        "constraints": field.constraints.model_dump(exclude_none=True)
        if field.constraints
        else None,
    }


ProfileOption = Annotated[str | None, typer.Option("--profile", "-p")]
VersionOption = Annotated[str | None, typer.Option("--version", "-v")]


@app.command("schema")
def schema(profile: ProfileOption = None, version: VersionOption = None) -> None:
    """Every entity type of a profile with its fields."""
    spec = _spec(profile, version)
    emit(
        {
            "profile": spec.name,
            "version": spec.version,
            "root_entity": spec.root_entity,
            "entities": {
                name: {
                    "description": entity.description,
                    "ontology_term": entity.ontology_term,
                    "fields": [_field_summary(f) for f in entity.fields],
                }
                for name, entity in spec.entities.items()
            },
        }
    )


@app.command("relationships")
def relationships(profile: ProfileOption = None, version: VersionOption = None) -> None:
    """Which entity types nest under which, and by what field."""
    spec = _spec(profile, version)
    emit(
        {
            "profile": spec.name,
            "version": spec.version,
            "root_entity": spec.root_entity,
            "entities": {
                name: {
                    "identifier": next(
                        (f.name for f in entity.fields if f.is_identifier), None
                    ),
                    "children": {
                        f.name: f.items
                        for f in entity.fields
                        if f.items and f.items in spec.entities
                    },
                    "references": {
                        f.name: f.reference
                        for f in entity.fields
                        if getattr(f, "reference", None)
                    },
                }
                for name, entity in spec.entities.items()
            },
        }
    )


@app.command("fields")
def fields(
    entity_type: Annotated[str, typer.Argument(help="Entity type")],
    profile: ProfileOption = None,
    version: VersionOption = None,
) -> None:
    """Every field of one entity type."""
    spec = _spec(profile, version)
    emit([_field_summary(f) for f in _entity(spec, entity_type).fields])


@app.command("required")
def required(
    entity_type: Annotated[str, typer.Argument(help="Entity type")],
    profile: ProfileOption = None,
    version: VersionOption = None,
) -> None:
    """The fields an entity of this type must carry."""
    spec = _spec(profile, version)
    emit([_field_summary(f) for f in _entity(spec, entity_type).fields if f.required])


@app.command("field")
def field(
    entity_type: Annotated[str, typer.Argument(help="Entity type")],
    field_name: Annotated[str, typer.Argument(help="Field name")],
    profile: ProfileOption = None,
    version: VersionOption = None,
) -> None:
    """One field's full specification."""
    spec = _spec(profile, version)
    entity = _entity(spec, entity_type)
    found = next((f for f in entity.fields if f.name == field_name), None)
    if found is None:
        echo_error(
            f"'{entity_type}' has no field '{field_name}'. "
            f"Available: {', '.join(f.name for f in entity.fields)}."
        )
        raise typer.Exit(ExitCode.INPUT_ERROR)
    emit(found.model_dump(exclude_none=True))
