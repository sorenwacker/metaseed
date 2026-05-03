"""Logging configuration for Metaseed.

This module provides centralized logging configuration. All modules should
use the standard logging pattern:

    import logging
    logger = logging.getLogger(__name__)

The logging level can be controlled via:
- METASEED_LOG_LEVEL environment variable
- Programmatic configuration via configure_logging()

Log Levels:
- DEBUG: Detailed diagnostic information
- INFO: General operational messages
- WARNING: Potential issues that don't prevent operation
- ERROR: Errors that prevent specific operations
- CRITICAL: Severe errors that may cause shutdown
"""

import logging
import os
import sys
from typing import TextIO

# Default log format
DEFAULT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Compact format for CLI
CLI_FORMAT = "%(levelname)s: %(message)s"


def configure_logging(
    level: str | int | None = None,
    format_string: str | None = None,
    stream: TextIO | None = None,
    cli_mode: bool = False,
) -> None:
    """Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) or int.
            Defaults to METASEED_LOG_LEVEL env var or WARNING.
        format_string: Custom format string. Defaults to standard format.
        stream: Output stream. Defaults to stderr.
        cli_mode: If True, use compact format suitable for CLI output.
    """
    if level is None:
        level = os.environ.get("METASEED_LOG_LEVEL", "WARNING")

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.WARNING)

    if format_string is None:
        format_string = CLI_FORMAT if cli_mode else DEFAULT_FORMAT

    if stream is None:
        stream = sys.stderr

    # Configure root logger for metaseed
    root_logger = logging.getLogger("metaseed")
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Add new handler
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)

    if cli_mode:
        formatter = logging.Formatter(format_string)
    else:
        formatter = logging.Formatter(format_string, datefmt=DEFAULT_DATE_FORMAT)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Prevent propagation to root logger
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module.

    Args:
        name: Module name (typically __name__).

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)
