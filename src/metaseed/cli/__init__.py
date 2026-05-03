"""CLI module for Metaseed."""

from pathlib import Path
from typing import Annotated

import typer
import yaml

from metaseed import __version__

# Import commands from submodules
from metaseed.cli.commands.example import export_example
from metaseed.cli.commands.merge import compare_profiles, merge_profiles
from metaseed.cli.output import CheckOutput, echo_error, echo_success
from metaseed.importers import ISAImporter
from metaseed.logging import configure_logging
from metaseed.models import get_model
from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.storage import JsonStorage, StorageError, YamlStorage
from metaseed.validators import DatasetValidator
from metaseed.validators import validate as validate_data


def _configure_logging_callback(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = "DEBUG" if verbose else "WARNING"
    configure_logging(level=level, cli_mode=True)


app = typer.Typer(
    name="metaseed",
    help="Tools for creating, editing, and validating experimental metadata following MIAPPE standards.",
    no_args_is_help=True,
)


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-V", help="Enable verbose logging")
    ] = False,
) -> None:
    """Metaseed CLI for metadata management."""
    _configure_logging_callback(verbose)


# Exit codes
EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 1
EXIT_INPUT_ERROR = 2
EXIT_CONFIG_ERROR = 3


def resolve_profile_version(profile: str | None, version: str | None) -> tuple[str, str]:
    """Resolve profile and version with smart defaults.

    Args:
        profile: Profile name, or None for default.
        version: Version string, or None for latest.

    Returns:
        Tuple of (profile, version) with defaults resolved.

    Raises:
        typer.Exit: If profile is unknown (exit code 3).
    """
    factory = ProfileFactory()

    if profile is None:
        profile = factory.get_default_profile()

    if profile not in factory.list_profiles():
        echo_error(f"Unknown profile '{profile}'")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if version is None:
        latest = factory.get_latest_version(profile)
        if latest is None:
            echo_error(f"No versions found for profile '{profile}'")
            raise typer.Exit(EXIT_CONFIG_ERROR)
        version = latest

    return profile, version


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"metaseed {__version__}")


@app.command()
def profiles(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed information")
    ] = False,
) -> None:
    """List available profiles and versions."""
    factory = ProfileFactory()
    profile_list = factory.get_profile_info()

    if not profile_list:
        typer.echo("No profiles available.")
        return

    if verbose:
        for info in profile_list:
            typer.echo(f"{info['name']}:")
            typer.echo(f"  versions: {', '.join(info['versions'])}")
            typer.echo(f"  latest: {info['latest']}")
    else:
        default = factory.get_default_profile()
        for info in profile_list:
            marker = " (default)" if info["name"] == default else ""
            typer.echo(f"  {info['name']}{marker}")


@app.command()
def validate(
    file: Annotated[Path, typer.Argument(help="Path to the file to validate")],
    entity: Annotated[str, typer.Option("--entity", "-e", help="Entity type")] = "investigation",
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile name")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v", help="Profile version")] = None,
) -> None:
    """Validate a metadata file against a profile."""
    profile, version = resolve_profile_version(profile, version)

    if not file.exists():
        echo_error(f"File not found: {file}")
        raise typer.Exit(EXIT_INPUT_ERROR)

    try:
        content = file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if data is None:
            data = {}
    except yaml.YAMLError as e:
        echo_error(f"Invalid YAML: {e}")
        raise typer.Exit(EXIT_INPUT_ERROR) from None

    errors = validate_data(data, entity, version, profile=profile)

    if errors:
        typer.echo(f"Validation failed with {len(errors)} error(s):")
        for error in errors:
            typer.echo(f"  - {error.field}: {error.message}")
        raise typer.Exit(EXIT_VALIDATION_ERROR)
    echo_success(f"Validation passed. File is valid {entity} ({profile} v{version}).")


@app.command()
def template(
    entity: Annotated[str, typer.Argument(help="Entity type to generate template for")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format")] = "yaml",
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile name")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v", help="Profile version")] = None,
) -> None:
    """Generate a template file for an entity."""
    profile, version = resolve_profile_version(profile, version)

    try:
        loader = SpecLoader(profile=profile)
        spec = loader.load_entity(entity.lower(), version)
    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_CONFIG_ERROR) from None

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
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile name")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v", help="Profile version")] = None,
) -> None:
    """Convert between YAML and JSON formats."""
    profile, version = resolve_profile_version(profile, version)

    if not input_file.exists():
        echo_error(f"File not found: {input_file}")
        raise typer.Exit(EXIT_INPUT_ERROR)

    try:
        Model = get_model(entity, version)
    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_CONFIG_ERROR) from None

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
        echo_success(f"Converted {input_file} to {output_file}")
    except StorageError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_INPUT_ERROR) from None


@app.command()
def entities(
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile name")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v", help="Profile version")] = None,
) -> None:
    """List available entities for a profile."""
    profile, version = resolve_profile_version(profile, version)

    try:
        loader = SpecLoader(profile=profile)
        entity_list = loader.list_entities(version)
    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_CONFIG_ERROR) from None

    typer.echo(f"Available entities ({profile} v{version}):")
    for entity in sorted(entity_list):
        typer.echo(f"  - {entity}")


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Path to file or directory to check")],
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile name")] = None,
    version: Annotated[str | None, typer.Option("--version", "-v", help="Profile version")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Show detailed information")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress non-error output")] = False,
) -> None:
    """Validate dataset with reference integrity checking.

    Checks a file or directory for:
    - Entity structure validation
    - Required field presence
    - Reference integrity (cross-entity references exist)
    """
    profile, version = resolve_profile_version(profile, version)

    if not path.exists():
        echo_error(f"Path not found: {path}")
        raise typer.Exit(EXIT_INPUT_ERROR)

    validator = DatasetValidator(profile=profile, version=version)
    output_formatter = CheckOutput(verbose=verbose, quiet=quiet)

    result = validator.validate_file(path) if path.is_file() else validator.validate_directory(path)

    output_formatter.print_result(result)

    if not result.is_valid:
        raise typer.Exit(EXIT_VALIDATION_ERROR)


@app.command(name="import")
def import_isa(
    path: Annotated[Path, typer.Argument(help="Path to ISA-JSON file or ISA-Tab directory")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output directory")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format")] = "yaml",
) -> None:
    """Import ISA-Tab or ISA-JSON data to MIAPPE format.

    Supports:
    - ISA-JSON: Single .json file
    - ISA-Tab: Directory containing i_*.txt, s_*.txt, a_*.txt files
    """
    importer = ISAImporter()

    try:
        if path.is_file() and path.suffix.lower() == ".json":
            result = importer.import_json(path)
            typer.echo(f"Imported ISA-JSON: {path.name}")
        elif path.is_dir():
            result = importer.import_tab(path)
            typer.echo(f"Imported ISA-Tab: {path.name}")
        else:
            typer.echo("Error: Path must be a .json file or directory", err=True)
            raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error importing: {e}", err=True)
        raise typer.Exit(1) from None

    # Print summary
    typer.echo(result.summary)

    # Show warnings if any
    for warning in result.warnings:
        typer.echo(f"  Warning: {warning}")

    # Output results
    if output:
        output.mkdir(parents=True, exist_ok=True)

        if format.lower() == "json":
            import json

            (output / "investigation.json").write_text(json.dumps(result.investigation, indent=2))
            for i, study in enumerate(result.studies):
                (output / f"study_{i + 1}.json").write_text(json.dumps(study, indent=2))
        else:
            (output / "investigation.yaml").write_text(
                yaml.dump(result.investigation, default_flow_style=False)
            )
            for i, study in enumerate(result.studies):
                (output / f"study_{i + 1}.yaml").write_text(
                    yaml.dump(study, default_flow_style=False)
                )

        typer.echo(f"Output written to: {output}")
    else:
        # Print investigation to stdout
        typer.echo("\n--- Investigation ---")
        typer.echo(yaml.dump(result.investigation, default_flow_style=False))

        if result.studies:
            typer.echo("--- Studies ---")
            for study in result.studies:
                typer.echo(yaml.dump(study, default_flow_style=False))


@app.command(name="ui")
def web_ui(
    host: Annotated[str, typer.Option("--host", "-h", help="Host to bind to")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to bind to")] = 8080,
) -> None:
    """Launch the web interface."""
    from metaseed.ui import run_ui

    typer.echo(f"Starting Metaseed web interface at http://{host}:{port}")
    run_ui(host=host, port=port)


# Register commands from submodules
app.command(name="example")(export_example)
app.command(name="compare")(compare_profiles)
app.command(name="merge")(merge_profiles)


if __name__ == "__main__":
    app()
