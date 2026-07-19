"""CLI output formatting helpers.

This module provides colored output functions and result formatting
for consistent CLI user experience.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Self

import typer

if TYPE_CHECKING:
    from metaseed.validators.dataset import DatasetValidationResult


class ExitCode(IntEnum):
    """Process exit codes used by the Metaseed CLI commands."""

    VALIDATION_ERROR = 1
    INPUT_ERROR = 2
    CONFIG_ERROR = 3


def echo_error(message: str) -> None:
    """Print an error message in red to stderr.

    Args:
        message: The error message to display.
    """
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)


def echo_success(message: str) -> None:
    """Print a success message in green.

    Args:
        message: The success message to display.
    """
    typer.secho(message, fg=typer.colors.GREEN)


def echo_warning(message: str) -> None:
    """Print a warning message in yellow.

    Args:
        message: The warning message to display.
    """
    typer.secho(f"Warning: {message}", fg=typer.colors.YELLOW)


class CheckOutput:
    """Formats and displays dataset validation results with colors.

    Example:
        >>> output = CheckOutput(verbose=True)
        >>> output.print_result(result)
    """

    def __init__(self: Self, verbose: bool = False, quiet: bool = False) -> None:
        """Initialize the output formatter.

        Args:
            verbose: If True, show detailed information.
            quiet: If True, suppress non-error output.
        """
        self.verbose = verbose
        self.quiet = quiet

    def print_result(self: Self, result: DatasetValidationResult) -> None:
        """Print validation result with appropriate formatting.

        Args:
            result: The dataset validation result to display.
        """
        if self.quiet and result.is_valid:
            return

        # Show files checked if verbose
        if self.verbose and result.files_checked:
            typer.echo("Files checked:")
            for path in result.files_checked:
                typer.echo(f"  - {path}")
            typer.echo()

        # Show entity counts if verbose
        if self.verbose and result.entity_counts:
            typer.echo("Entity counts:")
            for entity_type, count in sorted(result.entity_counts.items()):
                typer.echo(f"  {entity_type}: {count}")
            typer.echo()

        # Show warnings
        for warning in result.warnings:
            echo_warning(f"{warning.field}: {warning.message}")

        # Show errors
        for error in result.errors:
            typer.secho(f"  {error.field}: {error.message}", fg=typer.colors.RED)

        # Show summary
        if result.is_valid:
            if not self.quiet:
                echo_success("Validation passed.")
        else:
            error_count = len(result.errors)
            warning_count = len(result.warnings)
            typer.secho(
                f"Validation failed: {error_count} error(s), {warning_count} warning(s)",
                fg=typer.colors.RED,
            )
