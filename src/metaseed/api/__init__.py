"""Public API for metaseed.

This module provides the clean public API for working with metadata schemas.
Use MetaseedClient as the main entry point for programmatic access.

Example:
    >>> from metaseed.api import MetaseedClient
    >>> client = MetaseedClient("miappe", "1.2")
    >>> client.list_entity_types()
    ['Investigation', 'Study', 'Person', ...]

The hub (metaseed-hub) is the deployed REST surface; this package is the
Python client API.
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
from metaseed.api.schema import (
    EntitySchema,
    FieldInfo,
    ValidationIssue,
    ValidationResult,
)
from metaseed.api.serialization import SkippedNode

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
    "SkippedNode",
    "ValidationError",
    "ValidationIssue",
    "ValidationResult",
]
