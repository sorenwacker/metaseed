"""CLI commands for profile comparison and merging."""

from pathlib import Path
from typing import Annotated

import typer

from metaseed.cli.output import echo_error, echo_success
from metaseed.specs.loader import SpecLoadError

# Exit codes
EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 1
EXIT_INPUT_ERROR = 2
EXIT_CONFIG_ERROR = 3


def _parse_profile_spec(spec: str) -> tuple[str, str]:
    """Parse a profile/version specification.

    Args:
        spec: Profile spec in format "profile/version" (e.g., "miappe/1.1").

    Returns:
        Tuple of (profile, version).

    Raises:
        typer.Exit: If format is invalid.
    """
    if "/" not in spec:
        echo_error(f"Invalid profile format: '{spec}'. Use 'profile/version' (e.g., 'miappe/1.1')")
        raise typer.Exit(EXIT_INPUT_ERROR)

    parts = spec.split("/", 1)
    return parts[0], parts[1]


def compare_profiles(
    profiles: Annotated[
        list[str], typer.Argument(help="Profiles to compare (format: profile/version)")
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    format: Annotated[
        str, typer.Option("--format", "-f", help="Output format: markdown, csv, html")
    ] = "markdown",
) -> None:
    """Compare multiple profile specifications.

    Shows differences in entities, fields, and constraints across profiles.

    Examples:
        metaseed compare miappe/1.1 isa/1.0
        metaseed compare miappe/1.1 miappe/1.2 -o diff.md -f markdown
        metaseed compare miappe/1.1 isa/1.0 cropxr-phenotyping/0.0.5
    """
    if len(profiles) < 2:
        echo_error("At least 2 profiles required for comparison")
        raise typer.Exit(EXIT_INPUT_ERROR)

    # Parse profile specs
    profile_tuples = []
    for spec in profiles:
        profile_tuples.append(_parse_profile_spec(spec))

    try:
        from metaseed.specs.merge import (
            CSVReportGenerator,
            HTMLReportGenerator,
            MarkdownReportGenerator,
            compare,
        )

        result = compare(profile_tuples)

        # Generate report
        if format.lower() == "csv":
            report = CSVReportGenerator(result).generate()
        elif format.lower() == "html":
            report = HTMLReportGenerator(result).generate()
        else:
            report = MarkdownReportGenerator(result).generate()

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8")
            echo_success(f"Comparison report written to {output}")
        else:
            typer.echo(report)

        # Print summary
        stats = result.statistics
        typer.echo("")
        typer.echo(f"Compared {len(profiles)} profiles:")
        typer.echo(f"  Entities: {stats.total_entities} total, {stats.common_entities} common")
        typer.echo(f"  Fields: {stats.total_fields} total, {stats.conflicting_fields} conflicts")

    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_CONFIG_ERROR) from None
    except ValueError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_INPUT_ERROR) from None


def merge_profiles(
    profiles: Annotated[
        list[str], typer.Argument(help="Profiles to merge (format: profile/version)")
    ],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output YAML file path")] = Path(
        "merged.yaml"
    ),
    strategy: Annotated[
        str, typer.Option("--strategy", "-s", help="Merge strategy")
    ] = "first_wins",
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Name for merged profile")
    ] = None,
    version: Annotated[
        str, typer.Option("--version", "-v", help="Version for merged profile")
    ] = "1.0",
) -> None:
    """Merge multiple profile specifications into one.

    Combines entities and fields from multiple profiles with conflict resolution.

    Strategies:
        first_wins: Use first profile's values for conflicts
        last_wins: Use last profile's values for conflicts
        most_restrictive: required=True wins, tighter constraints
        least_restrictive: required=False wins, looser constraints
        prefer_<profile>: Always prefer specific profile (e.g., prefer_miappe/1.1)

    Examples:
        metaseed merge miappe/1.1 isa/1.0 -o combined.yaml
        metaseed merge miappe/1.1 cropxr-phenotyping/0.0.5 -s most_restrictive -o strict.yaml
        metaseed merge miappe/1.1 isa/1.0 -s prefer_miappe/1.1 -n miappe-extended
    """
    if len(profiles) < 2:
        echo_error("At least 2 profiles required for merge")
        raise typer.Exit(EXIT_INPUT_ERROR)

    # Parse profile specs
    profile_tuples = []
    for spec in profiles:
        profile_tuples.append(_parse_profile_spec(spec))

    # Default name from profiles
    if name is None:
        name = "-".join(p[0] for p in profile_tuples) + "-merged"

    try:
        from metaseed.specs.merge import merge

        result = merge(
            profiles=profile_tuples,
            strategy=strategy,
            output_name=name,
            output_version=version,
        )

        # Write output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.to_yaml(), encoding="utf-8")

        echo_success(f"Merged profile written to {output}")

        # Print summary
        typer.echo(f"  Name: {result.merged_profile.name}")
        typer.echo(f"  Version: {result.merged_profile.version}")
        typer.echo(f"  Entities: {len(result.merged_profile.entities)}")
        typer.echo(f"  Strategy: {result.strategy_used}")

        if result.warnings:
            typer.echo(f"  Warnings: {len(result.warnings)}")

        if result.has_unresolved_conflicts:
            typer.echo(f"  Unresolved conflicts: {len(result.unresolved_conflicts)}")

    except SpecLoadError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_CONFIG_ERROR) from None
    except ValueError as e:
        echo_error(str(e))
        raise typer.Exit(EXIT_INPUT_ERROR) from None
