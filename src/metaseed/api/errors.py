"""Public API exception hierarchy for metaseed.

This module defines the exception hierarchy for the public API
(`MetaseedClient` and related interfaces). External code should catch
these exceptions, not internal ones from `metaseed.core.exceptions`.

Hierarchy:
    MetaseedError (base)
    ├── ProfileNotFoundError - Profile or version not found
    ├── EntityNotFoundError - Entity ID not found in store
    ├── EntityTypeNotFoundError - Entity type not in profile
    └── ValidationError - Validation failed with details

Usage:
    >>> from metaseed import MetaseedClient
    >>> from metaseed.api.errors import ProfileNotFoundError
    >>>
    >>> try:
    ...     client = MetaseedClient("nonexistent", "1.0")
    ... except ProfileNotFoundError as e:
    ...     print(f"Profile '{e.profile}' not found")

Design:
    - Each exception includes structured attributes (not just messages)
    - Exceptions are specific to user-facing error conditions
    - Internal errors are caught at the API boundary and translated
"""

from __future__ import annotations


class MetaseedError(Exception):
    """Base exception for all metaseed errors.

    All public API exceptions inherit from this class, allowing users
    to catch all metaseed-related errors with a single except clause.

    Example:
        >>> try:
        ...     client.get_entity("nonexistent")
        ... except MetaseedError as e:
        ...     print(f"Metaseed error: {e}")
    """


class ProfileNotFoundError(MetaseedError):
    """Profile or version not found.

    Raised when attempting to create a client with a profile name
    or version that does not exist.

    Attributes:
        profile: The profile name that was not found.
        version: The version that was not found (if applicable).
    """

    def __init__(self, profile: str, version: str | None = None) -> None:
        """Initialize the error.

        Args:
            profile: Profile name that was not found.
            version: Version that was not found (optional).
        """
        self.profile = profile
        self.version = version

        if version:
            message = f"Profile '{profile}' version '{version}' not found"
        else:
            message = f"Profile '{profile}' not found"
        super().__init__(message)


class InvalidSpecError(MetaseedError):
    """A provided profile spec (dict or YAML file) is invalid or unreadable.

    Raised by the alternate constructors (``from_spec``, ``from_yaml``) so the
    caller catches a metaseed error rather than a leaked pydantic, YAML, or
    filesystem exception.

    Attributes:
        detail: The underlying reason the spec could not be loaded.
    """

    def __init__(self, detail: str) -> None:
        """Initialize the error.

        Args:
            detail: Description of why the spec is invalid.
        """
        self.detail = detail
        super().__init__(f"Invalid profile spec: {detail}")


class EntityNotFoundError(MetaseedError):
    """Entity not found in store.

    Raised when attempting to retrieve or modify an entity that does not exist.

    Attributes:
        entity_id: The ID of the entity that was not found.
    """

    def __init__(self, entity_id: str) -> None:
        """Initialize the error.

        Args:
            entity_id: ID of the entity that was not found.
        """
        self.entity_id = entity_id
        super().__init__(f"Entity with ID '{entity_id}' not found")


class EntityTypeNotFoundError(MetaseedError):
    """Entity type not found in profile.

    Raised when attempting to use an entity type that does not exist
    in the current profile.

    Attributes:
        entity_type: The entity type name that was not found.
        profile: The profile being used.
    """

    def __init__(self, entity_type: str, profile: str) -> None:
        """Initialize the error.

        Args:
            entity_type: Entity type name that was not found.
            profile: The profile where the type was expected.
        """
        self.entity_type = entity_type
        self.profile = profile
        super().__init__(
            f"Entity type '{entity_type}' not found in profile '{profile}'"
        )


class ValidationError(MetaseedError):
    """Validation failed.

    Raised when entity data fails validation. Contains detailed
    information about what failed.

    Attributes:
        errors: List of validation error details.
    """

    def __init__(self, errors: list[dict[str, str]]) -> None:
        """Initialize the error.

        Args:
            errors: List of error dictionaries with 'field', 'message', and 'rule' keys.
        """
        self.errors = errors
        error_count = len(errors)
        if error_count == 1:
            message = f"Validation failed: {errors[0].get('message', 'Unknown error')}"
        else:
            message = f"Validation failed with {error_count} errors"
        super().__init__(message)
