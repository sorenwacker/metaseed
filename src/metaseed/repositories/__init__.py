"""Repository module for entity storage.

This module provides abstract interfaces and implementations for
entity persistence, following the same DI pattern as SpecPersistence.
"""

from metaseed.repositories.base import EntityData, EntityRepository
from metaseed.repositories.file import FileEntityRepository
from metaseed.repositories.helpers import (
    IDENTIFIER_FIELDS,
    LABEL_FIELDS,
    derive_label,
    find_parent_ref_field,
    get_identifier,
    get_identifier_from_instance,
    update_parent_reference,
)
from metaseed.repositories.memory import MemoryEntityRepository

__all__ = [
    "EntityData",
    "EntityRepository",
    "FileEntityRepository",
    "MemoryEntityRepository",
    "IDENTIFIER_FIELDS",
    "LABEL_FIELDS",
    "derive_label",
    "find_parent_ref_field",
    "get_identifier",
    "get_identifier_from_instance",
    "update_parent_reference",
]
