"""Public API for metaseed.

This module provides the clean public API for working with metadata schemas.
Use MetaseedClient as the main entry point for programmatic access.

Example:
    >>> from metaseed.api import MetaseedClient
    >>> client = MetaseedClient("miappe", "1.2")
    >>> client.list_entity_types()
    ['Investigation', 'Study', 'Person', ...]

For REST API access, see metaseed.api.rest.
"""

from typing import TYPE_CHECKING

from metaseed.api.client import MetaseedClient
from metaseed.api.entities import Entity, EntityNode
from metaseed.api.errors import (
    EntityNotFoundError,
    EntityTypeNotFoundError,
    InvalidSpecError,
    MetaseedError,
    ProfileNotFoundError,
    ValidationError,
)
from metaseed.api.schema import (
    EntitySchema,
    FieldInfo,
    ValidationIssue,
    ValidationResult,
)

if TYPE_CHECKING:
    from metaseed.api.rest import app


def __getattr__(name: str) -> object:
    """Lazily expose the FastAPI ``app``.

    Importing it eagerly would pull FastAPI/Starlette into every consumer that
    imports ``metaseed`` (or any submodule), defeating the framework-agnostic
    boundary. ``from metaseed.api import app`` still works — it loads on access.
    """
    if name == "app":
        from metaseed.api.rest import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Entity",
    "EntityNode",
    "EntityNotFoundError",
    "EntitySchema",
    "EntityTypeNotFoundError",
    "FieldInfo",
    "InvalidSpecError",
    "MetaseedClient",
    "MetaseedError",
    "ProfileNotFoundError",
    "ValidationError",
    "ValidationIssue",
    "ValidationResult",
    "app",
]
