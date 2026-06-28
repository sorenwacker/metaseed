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

# Re-export the FastAPI app for backward compatibility
from metaseed.api.rest import app
from metaseed.api.schema import (
    EntitySchema,
    FieldInfo,
    ValidationIssue,
    ValidationResult,
)

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
