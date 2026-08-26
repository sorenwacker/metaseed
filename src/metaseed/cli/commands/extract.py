"""`metaseed extract` — reading metadata out of spreadsheets and documents.

The same path the MCP server's extraction tools take: parse a file with
:func:`metaseed.agent.core.parse_file`, suggest a mapping with
:func:`metaseed.agent.mapping.suggest_mapping`, then extract rows through an
:class:`~metaseed.agent.core.ExtractionContext`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit

app = typer.Typer(
    name="extract", no_args_is_help=True, help="Extract metadata from files."
)

ProfileOption = Annotated[str | None, typer.Option("--profile", "-p")]
VersionOption = Annotated[str | None, typer.Option("--version", "-v")]


def _profile(profile: str | None, version: str | None) -> Any:
    from metaseed.cli.app import resolve_profile_version
    from metaseed.specs.loader import SpecLoader

    name, resolved = resolve_profile_version(profile, version)
    try:
        return SpecLoader().load_profile(version=resolved, profile=name)
    except Exception as exc:
        echo_error(f"Could not load profile {name} {resolved}: {exc}")
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc


def _parsed(source: Path) -> Any:
    from metaseed.agent.core import parse_file

    if not source.exists():
        echo_error(f"No such file: {source}")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    try:
        return parse_file(source)
    except ValueError as exc:
        echo_error(f"{source} could not be parsed: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc


def _entity_spec(profile: Any, entity: str) -> Any:
    spec = profile.entities.get(entity)
    if spec is None:
        echo_error(
            f"'{entity}' is not an entity of {profile.name} {profile.version}. "
            f"Available: {', '.join(sorted(profile.entities))}."
        )
        raise typer.Exit(ExitCode.INPUT_ERROR)
    return spec


@app.command("parse")
def parse(source: Annotated[Path, typer.Argument(help="The file to read")]) -> None:
    """Show what a source file holds: its tables, columns and first rows."""
    content = _parsed(source)
    emit(
        {
            "file": str(source),
            "format": content.format,
            "tables": [
                {
                    "columns": table.headers,
                    "rows": len(table.rows),
                    "sample": table.rows[:3],
                }
                for table in content.tables
            ],
            "text_blocks": content.text_blocks[:5] if content.text_blocks else [],
            "metadata": content.metadata,
        }
    )


@app.command("analyze")
def analyze(
    source: Annotated[Path, typer.Argument(help="The file to read")],
    entity: Annotated[
        str, typer.Option("--entity", "-e", help="Entity type to map onto")
    ],
    table: Annotated[int, typer.Option("--table", help="Which table in the file")] = 0,
    profile: ProfileOption = None,
    version: VersionOption = None,
) -> None:
    """Suggest which column feeds which field, with a confidence for each."""
    from metaseed.agent.mapping import suggest_mapping

    content = _parsed(source)
    if not content.tables:
        echo_error(f"{source} holds no tables to map.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    spec = _entity_spec(_profile(profile, version), entity)
    columns = content.tables[table].headers
    suggestions = suggest_mapping(columns, spec)
    emit(
        {
            "file": str(source),
            "entity": entity,
            "columns": columns,
            "mappings": [
                {
                    "field": mapping.field_name,
                    "column": mapping.source_column,
                    "confidence": mapping.confidence,
                }
                for mapping in suggestions
            ],
            "unmapped_fields": sorted(
                {field.name for field in spec.fields}
                - {m.field_name for m in suggestions}
            ),
        }
    )


@app.command("run")
def run(
    source: Annotated[Path, typer.Argument(help="The file to read")],
    entity: Annotated[
        str, typer.Option("--entity", "-e", help="Entity type to extract")
    ],
    table: Annotated[int, typer.Option("--table", help="Which table in the file")] = 0,
    mapping_file: Annotated[
        Path | None,
        typer.Option("--mapping", "-m", help="A mapping from `extract analyze`"),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the records here")
    ] = None,
    profile: ProfileOption = None,
    version: VersionOption = None,
) -> None:
    """Extract entity records from a file, through a suggested or given mapping."""
    from metaseed.agent.core import ExtractionContext
    from metaseed.agent.mapping import create_mapping, suggest_mapping

    spec_profile = _profile(profile, version)
    spec = _entity_spec(spec_profile, entity)
    context = ExtractionContext(spec_profile)
    content = context.add_source(source)
    if not content.tables:
        echo_error(f"{source} holds no tables to extract from.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    if mapping_file is not None:
        from metaseed.agent.mapping import FieldMapping

        raw = json.loads(mapping_file.read_text())
        pairs = raw.get("mappings", raw)
        field_mappings = [
            FieldMapping(
                field_name=item["field"],
                source_column=item["column"],
                confidence=item.get("confidence", 1.0),
            )
            for item in pairs
        ]
    else:
        field_mappings = suggest_mapping(content.tables[table].headers, spec)
    mapping = create_mapping(entity, field_mappings)
    result = context.extract_entities(0, entity, mapping=mapping, table_index=table)
    payload = {
        "entity": entity,
        "extracted": result.instances,
        "issues": [issue.model_dump() for issue in result.errors],
    }
    if output is None:
        emit(payload)
    else:
        output.write_text(json.dumps(payload, indent=2, default=str))
        echo_success(f"Wrote {len(result.instances)} {entity} records to {output}.")
    if result.errors:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("validate")
def validate(
    records: Annotated[Path, typer.Argument(help="Records from `extract run`")],
    entity: Annotated[
        str, typer.Option("--entity", "-e", help="Entity type of the records")
    ],
    profile: ProfileOption = None,
    version: VersionOption = None,
) -> None:
    """Check extracted records against the profile before they become entities."""
    from metaseed.agent.core import ExtractionContext

    if not records.exists():
        echo_error(f"No such file: {records}")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    payload = json.loads(records.read_text())
    instances = (
        payload.get("extracted", payload) if isinstance(payload, dict) else payload
    )
    context = ExtractionContext(_profile(profile, version))
    issues = []
    for position, instance in enumerate(instances):
        for issue in context.validate_instance(instance, entity):
            issues.append({"record": position, **issue.model_dump()})
    emit({"records": len(instances), "valid": not issues, "issues": issues})
    if issues:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command("export")
def export(
    records: Annotated[Path, typer.Argument(help="Records from `extract run`")],
    output: Annotated[Path, typer.Argument(help="Where to write them")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="json or yaml")] = "json",
) -> None:
    """Write extracted records out as JSON or YAML."""
    import yaml

    if not records.exists():
        echo_error(f"No such file: {records}")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    payload = json.loads(records.read_text())
    if fmt not in ("json", "yaml"):
        echo_error("Format is 'json' or 'yaml'.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    output.write_text(
        json.dumps(payload, indent=2, default=str)
        if fmt == "json"
        else yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    )
    echo_success(f"Wrote {output}.")
