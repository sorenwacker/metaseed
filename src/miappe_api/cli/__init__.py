"""CLI module for MIAPPE-API."""

from pathlib import Path
from typing import Annotated

import typer
import yaml

from miappe_api import __version__
from miappe_api.models import get_model
from miappe_api.specs.loader import SpecLoader, SpecLoadError
from miappe_api.storage import JsonStorage, StorageError, YamlStorage
from miappe_api.validators import validate as validate_data

app = typer.Typer(
    name="miappe",
    help="Schema-driven CLI for MIAPPE-compliant phenotyping metadata.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"miappe-api {__version__}")


@app.command()
def validate(
    file: Annotated[Path, typer.Argument(help="Path to the file to validate")],
    entity: Annotated[str, typer.Option("--entity", "-e", help="Entity type")] = "investigation",
    version: Annotated[str, typer.Option("--version", "-v", help="MIAPPE version")] = "1.1",
) -> None:
    """Validate a MIAPPE metadata file."""
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(1)

    try:
        content = file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if data is None:
            data = {}
    except yaml.YAMLError as e:
        typer.echo(f"Error: Invalid YAML: {e}", err=True)
        raise typer.Exit(1) from None

    errors = validate_data(data, entity, version)

    if errors:
        typer.echo(f"Validation failed with {len(errors)} error(s):")
        for error in errors:
            typer.echo(f"  - {error.field}: {error.message}")
        raise typer.Exit(1)
    else:
        typer.echo(f"Validation passed. File is valid {entity} (v{version}).")


@app.command()
def template(
    entity: Annotated[str, typer.Argument(help="Entity type to generate template for")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format")] = "yaml",
    version: Annotated[str, typer.Option("--version", "-v", help="MIAPPE version")] = "1.1",
) -> None:
    """Generate a template file for an entity."""
    try:
        loader = SpecLoader()
        spec = loader.load_entity(entity.lower(), version)
    except SpecLoadError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    # Build template with empty/example values
    template_data = {}
    for field in spec.fields:
        if field.required:
            if field.type.value == "string":
                template_data[field.name] = f"<{field.name}>"
            elif field.type.value == "integer":
                template_data[field.name] = 0
            elif field.type.value == "float":
                template_data[field.name] = 0.0
            elif field.type.value == "boolean":
                template_data[field.name] = False
            elif field.type.value == "date":
                template_data[field.name] = "2024-01-01"
            elif field.type.value == "datetime":
                template_data[field.name] = "2024-01-01T00:00:00"
            elif field.type.value == "list":
                template_data[field.name] = []
            else:
                template_data[field.name] = None
        else:
            # Add commented example for optional fields
            template_data[f"# {field.name}"] = None

    # Generate output
    if format.lower() == "json":
        import json

        content = json.dumps(template_data, indent=2)
    else:
        content = yaml.dump(template_data, default_flow_style=False, sort_keys=False)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        typer.echo(f"Template written to {output}")
    else:
        typer.echo(content)


@app.command()
def convert(
    input_file: Annotated[Path, typer.Argument(help="Input file path")],
    output_file: Annotated[Path, typer.Argument(help="Output file path")],
    entity: Annotated[str, typer.Option("--entity", "-e", help="Entity type")] = "investigation",
    version: Annotated[str, typer.Option("--version", "-v", help="MIAPPE version")] = "1.1",
) -> None:
    """Convert between YAML and JSON formats."""
    if not input_file.exists():
        typer.echo(f"Error: File not found: {input_file}", err=True)
        raise typer.Exit(1)

    try:
        Model = get_model(entity, version)
    except SpecLoadError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    # Determine input format
    input_suffix = input_file.suffix.lower()
    if input_suffix in [".yaml", ".yml"]:
        input_storage = YamlStorage()
    elif input_suffix == ".json":
        input_storage = JsonStorage()
    else:
        typer.echo(f"Error: Unknown input format: {input_suffix}", err=True)
        raise typer.Exit(1)

    # Determine output format
    output_suffix = output_file.suffix.lower()
    if output_suffix in [".yaml", ".yml"]:
        output_storage = YamlStorage()
    elif output_suffix == ".json":
        output_storage = JsonStorage()
    else:
        typer.echo(f"Error: Unknown output format: {output_suffix}", err=True)
        raise typer.Exit(1)

    try:
        entity_instance = input_storage.load(input_file, Model)
        output_storage.save(entity_instance, output_file)
        typer.echo(f"Converted {input_file} to {output_file}")
    except StorageError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None


@app.command()
def entities(
    version: Annotated[str, typer.Option("--version", "-v", help="MIAPPE version")] = "1.1",
) -> None:
    """List available MIAPPE entities."""
    try:
        loader = SpecLoader()
        entity_list = loader.list_entities(version)
    except SpecLoadError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Available entities (MIAPPE v{version}):")
    for entity in sorted(entity_list):
        typer.echo(f"  - {entity}")


@app.command(name="ui")
def web_ui(
    host: Annotated[str, typer.Option("--host", "-h", help="Host to bind to")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to bind to")] = 8080,
) -> None:
    """Launch the web interface."""
    from miappe_api.ui import run_ui

    typer.echo(f"Starting MIAPPE-API web interface at http://{host}:{port}")
    run_ui(host=host, port=port)


if __name__ == "__main__":
    app()
