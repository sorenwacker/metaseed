"""Typer application and command implementations for the Metaseed CLI.

The ``app`` object is re-exported from :mod:`metaseed.cli` and wired as the
``metaseed`` console script.
"""

from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

try:
    from metaseed._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Import commands from submodules
from metaseed.cli.commands.example import export_example
from metaseed.cli.commands.merge import compare_profiles, merge_profiles
from metaseed.cli.output import CheckOutput, ExitCode, echo_error, echo_success
from metaseed.logging import configure_logging
from metaseed.models import get_model
from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.storage import JsonStorage, StorageError, YamlStorage
from metaseed.storage.base import StorageBackend
from metaseed.validators import DatasetValidator
from metaseed.validators import validate as validate_data


def _configure_logging_callback(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = "DEBUG" if verbose else "WARNING"
    configure_logging(level=level, cli_mode=True)


app = typer.Typer(
    name="metaseed",
    help="Create, edit and validate research metadata against a chosen standard (MIAPPE, ISA, Darwin Core, DiSSCo, ENA, MetaboLights, PRIDE and others).",
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


def resolve_profile_version(
    profile: str | None, version: str | None
) -> tuple[str, str]:
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
        raise typer.Exit(ExitCode.CONFIG_ERROR)

    if version is None:
        latest = factory.get_latest_version(profile)
        if latest is None:
            echo_error(f"No versions found for profile '{profile}'")
            raise typer.Exit(ExitCode.CONFIG_ERROR)
        version = latest

    return profile, version


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"metaseed {__version__}")


@app.command()
def profiles(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-V", help="Show detailed information")
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
    entity: Annotated[
        str, typer.Option("--entity", "-e", help="Entity type")
    ] = "investigation",
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile name")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", "-v", help="Profile version")
    ] = None,
) -> None:
    """Validate a metadata file against a profile."""
    profile, version = resolve_profile_version(profile, version)

    if not file.exists():
        echo_error(f"File not found: {file}")
        raise typer.Exit(ExitCode.INPUT_ERROR)

    try:
        content = file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if data is None:
            data = {}
    except yaml.YAMLError as e:
        echo_error(f"Invalid YAML: {e}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from None

    from metaseed.specs.loader import SpecLoadError

    try:
        errors = validate_data(data, entity, version, profile=profile)
    except SpecLoadError as e:
        # An unknown entity/profile is the caller's mistake — a clear message
        # and a clean exit, like every sibling command, not a traceback.
        echo_error(str(e))
        raise typer.Exit(ExitCode.INPUT_ERROR) from None

    # Profile-specific structural checks (e.g. PRIDE's submission.px rules)
    # declare themselves as `validate` actions; running them here makes them
    # reachable from a shell instead of only as library calls.
    from metaseed.adapters import actions_for_profile

    profile_checks = list(actions_for_profile(profile, kind="validate"))
    if profile_checks:
        from metaseed.api.client import MetaseedClient

        client = MetaseedClient(profile, version)
        client.create_entity(entity, data, skip_validation=True)
        for action in profile_checks:
            errors.extend(action.resolve()(client))

    if errors:
        typer.echo(f"Validation failed with {len(errors)} error(s):")
        for error in errors:
            typer.echo(f"  - {error.field}: {error.message}")
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    echo_success(f"Validation passed. File is valid {entity} ({profile} v{version}).")


@app.command()
def template(
    entity: Annotated[str, typer.Argument(help="Entity type to generate template for")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output file path")
    ] = None,
    format: Annotated[
        str, typer.Option("--format", "-f", help="Output format")
    ] = "yaml",
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile name")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", "-v", help="Profile version")
    ] = None,
) -> None:
    """Generate a template file for an entity."""
    profile, version = resolve_profile_version(profile, version)

    try:
        loader = SpecLoader(profile=profile)
        spec = loader.load_entity(entity.lower(), version)
    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(ExitCode.CONFIG_ERROR) from None

    # Build template with empty/example values.
    # The "# name" comment-key technique is YAML-specific, so optional fields
    # are only represented for YAML output and omitted for JSON.
    is_yaml = format.lower() != "json"
    template_data: dict[str, Any] = {}
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
        elif is_yaml:
            # Add commented example for optional fields (YAML only)
            template_data[f"# {field.name}"] = None

    # Generate output
    if is_yaml:
        content = yaml.dump(template_data, default_flow_style=False, sort_keys=False)
    else:
        import json

        content = json.dumps(template_data, indent=2)

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
    entity: Annotated[
        str, typer.Option("--entity", "-e", help="Entity type")
    ] = "investigation",
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile name")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", "-v", help="Profile version")
    ] = None,
) -> None:
    """Convert between YAML and JSON formats."""
    profile, version = resolve_profile_version(profile, version)

    if not input_file.exists():
        echo_error(f"File not found: {input_file}")
        raise typer.Exit(ExitCode.INPUT_ERROR)

    try:
        Model = get_model(entity, version, profile)
    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(ExitCode.CONFIG_ERROR) from None

    # Determine input format
    input_suffix = input_file.suffix.lower()
    input_storage: StorageBackend
    if input_suffix in [".yaml", ".yml"]:
        input_storage = YamlStorage()
    elif input_suffix == ".json":
        input_storage = JsonStorage()
    else:
        echo_error(f"Unknown input format: {input_suffix}")
        raise typer.Exit(ExitCode.INPUT_ERROR)

    # Determine output format
    output_suffix = output_file.suffix.lower()
    output_storage: StorageBackend
    if output_suffix in [".yaml", ".yml"]:
        output_storage = YamlStorage()
    elif output_suffix == ".json":
        output_storage = JsonStorage()
    else:
        echo_error(f"Unknown output format: {output_suffix}")
        raise typer.Exit(ExitCode.INPUT_ERROR)

    try:
        entity_instance = input_storage.load(input_file, Model)
        output_storage.save(entity_instance, output_file)
        echo_success(f"Converted {input_file} to {output_file}")
    except StorageError as e:
        echo_error(str(e))
        raise typer.Exit(ExitCode.INPUT_ERROR) from None


@app.command()
def entities(
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile name")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", "-v", help="Profile version")
    ] = None,
) -> None:
    """List available entities for a profile."""
    profile, version = resolve_profile_version(profile, version)

    try:
        loader = SpecLoader(profile=profile)
        entity_list = loader.list_entities(version)
    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(ExitCode.CONFIG_ERROR) from None

    typer.echo(f"Available entities ({profile} v{version}):")
    for entity in sorted(entity_list):
        typer.echo(f"  - {entity}")


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Path to file or directory to check")],
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile name")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", "-v", help="Profile version")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show detailed information")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress non-error output")
    ] = False,
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
        raise typer.Exit(ExitCode.INPUT_ERROR)

    validator = DatasetValidator(profile=profile, version=version)
    output_formatter = CheckOutput(verbose=verbose, quiet=quiet)

    result = (
        validator.validate_file(path)
        if path.is_file()
        else validator.validate_directory(path)
    )

    output_formatter.print_result(result)

    if not result.is_valid:
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command(name="ui")
def web_ui(
    host: Annotated[
        str, typer.Option("--host", "-h", help="Host to bind to")
    ] = "127.0.0.1",
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


@app.command(name="mcp")
def mcp_server(
    transport: Annotated[
        str, typer.Option("--transport", "-t", help="Transport type (stdio or http)")
    ] = "stdio",
    host: Annotated[
        str, typer.Option("--host", "-h", help="Host for HTTP transport")
    ] = "127.0.0.1",
    port: Annotated[
        int, typer.Option("--port", "-p", help="Port for HTTP transport")
    ] = 8000,
) -> None:
    """Start the MCP (Model Context Protocol) server.

    The MCP server exposes metaseed functionality to MCP-compatible clients
    like Claude Desktop. It provides tools for parsing files, analyzing
    column mappings, extracting metadata, and validating results.

    Use 'stdio' transport for Claude Desktop integration.
    Use 'http' transport for debugging or web-based clients.
    """
    from metaseed.agent.mcp import run_server

    if transport == "http":
        typer.echo(f"Starting MCP server at http://{host}:{port}")
        run_server(transport="streamable-http", host=host, port=port)
    else:
        # stdio mode - no output to stdout as it would interfere with protocol
        run_server(transport="stdio")


@app.command(name="migrate")
def migrate_datasets(
    apply: Annotated[
        bool, typer.Option("--apply", help="Apply changes (default is dry run)")
    ] = False,
) -> None:
    """Migrate datasets to use unique_id for entity references.

    By default runs in dry-run mode showing what would change.
    Use --apply to actually save the changes.

    This migrates:
    - _parent_id (node ID) -> _parent_unique_id
    - Entity reference fields (e.g., material_source) from node IDs to unique_ids
    """
    from metaseed.cli.migrate import migrate_all_datasets, print_migration_report

    if not apply:
        typer.echo("DRY RUN - use --apply to save changes\n")
    else:
        typer.echo("APPLYING CHANGES\n")

    reports = migrate_all_datasets(dry_run=not apply)
    print_migration_report(reports)

    # Same contract as migrate-specs: scripted callers read the exit code,
    # and a failed dataset migration must not report success.
    if any("error" in report for report in reports):
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


@app.command(name="migrate-specs")
def migrate_spec_versions(
    apply: Annotated[
        bool, typer.Option("--apply", help="Write changes (default is dry run)")
    ] = False,
) -> None:
    """Repair profile specs whose version is not MAJOR.MINOR.

    Since 0.22 a spec version must match ^\\d+\\.\\d+$, so a spec written by an
    earlier release (for example version '1.2-dev-a1b2c3') is listed but cannot
    be loaded. This scans the built-in and user spec directories and normalizes
    those values, rewriting the version and nothing else.

    Values with no derivable version, and repairs that would put two specs at
    the same name+version path, are reported rather than guessed or overwritten.
    """
    from metaseed.cli import migrate_specs

    if not apply:
        typer.echo("DRY RUN - use --apply to write changes")
    else:
        typer.echo("APPLYING CHANGES")

    migrations = migrate_specs.migrate_spec_versions(dry_run=not apply)
    migrate_specs.print_migration_report(migrations, dry_run=not apply)

    if apply and migrate_specs.has_failures(migrations):
        raise typer.Exit(ExitCode.VALIDATION_ERROR)


if __name__ == "__main__":
    app()
