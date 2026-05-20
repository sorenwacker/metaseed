"""Repository module for entity and dataset storage.

This module provides abstract interfaces and implementations for
entity and dataset persistence, following the same DI pattern as SpecPersistence.
"""

from metaseed.repositories.base import EntityData, EntityRepository
from metaseed.repositories.dataset_repository import (
    AsyncDatasetRepository,
    DatasetData,
    DatasetInfo,
    DatasetRepository,
    validate_dataset_name,
)
from metaseed.repositories.file import FileEntityRepository
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
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
    "AsyncDatasetRepository",
    "DatasetData",
    "DatasetInfo",
    "DatasetRepository",
    "EntityData",
    "EntityRepository",
    "FileEntityRepository",
    "FilesystemDatasetRepository",
    "MemoryEntityRepository",
    "IDENTIFIER_FIELDS",
    "LABEL_FIELDS",
    "derive_label",
    "find_parent_ref_field",
    "get_identifier",
    "get_identifier_from_instance",
    "update_parent_reference",
    "validate_dataset_name",
]
