"""Internal exception hierarchy for metaseed core operations.

This module defines exceptions for internal use within the core, models,
specs, and storage modules. These exceptions are implementation details
and should not be caught by external code.

For public API exceptions, see `metaseed.api.errors`.

Hierarchy:
    MiappeError (base)
    ├── SpecError - YAML spec loading/parsing errors
    ├── ModelError - Pydantic model generation errors
    ├── ValidationFailedError - Entity validation failures
    └── StorageIOError - File I/O errors

Usage:
    Internal code raises these exceptions. The public API layer
    (`MetaseedClient`) catches them and re-raises as public exceptions
    (`MetaseedError` subclasses) with user-friendly messages.

Note:
    The name `MiappeError` is a legacy artifact from when the project
    was MIAPPE-specific. It remains for backward compatibility.
"""


class MiappeError(Exception):
    """Base exception for MIAPPE-API errors.

    All custom exceptions in the package inherit from this class.
    """


class SpecError(MiappeError):
    """Exception raised for specification-related errors.

    This includes errors loading, parsing, or validating YAML specifications.
    """


class ModelError(MiappeError):
    """Exception raised for model-related errors.

    This includes errors generating, registering, or accessing Pydantic models.
    """


class ValidationFailedError(MiappeError):
    """Exception raised when validation fails.

    This is raised when entity data fails validation rules.
    """


class StorageIOError(MiappeError):
    """Exception raised for storage-related I/O errors.

    This includes errors reading from or writing to files.
    """
