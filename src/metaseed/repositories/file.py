"""File-based entity repository implementation.

Persists entities to JSON files, suitable for sharing state between
processes (UI, MCP) and for use in metaseed-hub.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from metaseed.paths import user_data_base
from metaseed.repositories.base import EntityData, EntityRepository
from metaseed.repositories.helpers import (
    derive_label,
    find_parent_ref_field,
    get_identifier,
    normalize_reference_fields,
    remove_parent_reference,
    update_parent_reference,
)

logger = logging.getLogger(__name__)

DEFAULT_DATASETS_DIR = user_data_base() / "datasets"
"""Where datasets live when nothing overrides it.

Derived from the same base as every other metaseed data directory, so
``XDG_DATA_HOME`` (and ``%LOCALAPPDATA%`` on Windows) is honoured here as it
is for specs. It was hardcoded to ``~/.local/share`` in two places, which
meant a redirected data directory silently kept datasets in the real one.
"""


class FileEntityRepository(EntityRepository):
    """File-based entity repository.

    Stores entities as JSON files with hierarchy metadata.
    Multiple processes can share the same file for state synchronization.

    File format — a FLAT entity list; hierarchy is carried by ``parent_id``
    only. ``_load`` iterates the top-level list and does not recurse, so a
    file written with children nested inside entities would have every
    nested entity silently dropped:
    {
        "profile": "miappe",
        "version": "1.2",
        "modified": "2024-01-15T10:30:00",
        "entities": [
            {
                "id": "abc123",
                "entity_type": "Investigation",
                "label": "My Investigation",
                "data": { ... },
                "parent_id": null
            }
        ]
    }
    """

    def __init__(
        self: Self,
        dataset_path: Path | None = None,
        profile: str = "miappe",
        version: str | None = None,
    ) -> None:
        """Initialize the file repository.

        Args:
            dataset_path: Path to the JSON file. If None, the repository holds
                data in memory only and every save is skipped with a warning —
                use :meth:`from_dataset_name` for the default location.
            profile: Initial profile name.
            version: Initial version, None for latest.
        """
        self._path = dataset_path
        self._profile = profile
        self._version = version
        self._facade: Any = None  # Lazy loaded
        self._entities: dict[str, EntityData] = {}
        self._tree: list[EntityData] = []

        # Load existing data if file exists
        if self._path and self._path.exists():
            self._load()

    @classmethod
    def from_dataset_name(
        cls,
        name: str,
        datasets_dir: Path | None = None,
    ) -> FileEntityRepository:
        """Create repository from dataset name.

        Args:
            name: Dataset name (without .json extension).
            datasets_dir: Optional custom datasets directory.

        Returns:
            FileEntityRepository instance.
        """
        from metaseed.repositories.filesystem_dataset import default_datasets_dir

        # Shared resolver, not the bare constant: METASEED_DATASETS_DIR must
        # redirect this repository exactly as it does the dataset repository,
        # or a sandboxed run writes half its data into the real user dir.
        base_dir = datasets_dir or default_datasets_dir()
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"{name}.json"
        return cls(dataset_path=path)

    def _get_facade(self: Self) -> Any:
        """Get or create the ProfileFacade."""
        from metaseed.facade import ProfileFacade

        if self._facade is None or self._facade.profile != self._profile:
            self._facade = ProfileFacade(self._profile, self._version)
        return self._facade

    def _load(self: Self) -> None:
        """Load entities from file."""
        if not self._path or not self._path.exists():
            return

        try:
            with open(self._path) as f:
                data = json.load(f)

            self._profile = data.get("profile", self._profile)
            self._version = data.get("version", self._version)

            raw_entities = data.get("entities", [])
            entities, parent_map = self._parse_entities(raw_entities)
            self._entities = entities
            self._tree = self._build_hierarchy(entities, parent_map)

            logger.info(
                "Loaded %d entities from %s",
                len(self._entities),
                self._path,
            )

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load dataset: %s", e)

    def _parse_entities(
        self: Self, raw_entities: list[dict[str, Any]]
    ) -> tuple[dict[str, EntityData], dict[str, list[EntityData]]]:
        """Parse raw entity dictionaries into EntityData objects.

        Args:
            raw_entities: List of raw entity dicts from JSON.

        Returns:
            Tuple of (entities_by_id, parent_to_children_map).
        """
        entities: dict[str, EntityData] = {}
        parent_map: dict[str, list[EntityData]] = {}

        for raw in raw_entities:
            entity = EntityData(
                id=raw.get("id") or raw.get("_node_id") or str(uuid.uuid4())[:8],
                entity_type=raw.get("entity_type") or raw.get("_type", "Unknown"),
                label=raw.get("label", ""),
                data={
                    k: v
                    for k, v in raw.items()
                    if not k.startswith("_")
                    and k not in ("id", "entity_type", "label", "parent_id", "children")
                },
                parent_id=raw.get("parent_id") or raw.get("_parent_id"),
            )

            # Derive label if not present
            if not entity.label:
                helper = getattr(self._get_facade(), entity.entity_type, None)
                spec = helper._spec if helper else None
                entity.label = derive_label(entity.entity_type, entity.data, spec=spec)

            entities[entity.id] = entity

            # Track parent relationships
            if entity.parent_id:
                if entity.parent_id not in parent_map:
                    parent_map[entity.parent_id] = []
                parent_map[entity.parent_id].append(entity)

        return entities, parent_map

    def _build_hierarchy(
        self: Self,
        entities: dict[str, EntityData],
        parent_map: dict[str, list[EntityData]],
    ) -> list[EntityData]:
        """Build tree hierarchy from flat entity list.

        Args:
            entities: Dict of entities by ID.
            parent_map: Dict mapping parent IDs to their children.

        Returns:
            List of root entities with children populated.
        """
        tree: list[EntityData] = []

        # Assign children to parents
        for parent_id, children in parent_map.items():
            if parent_id in entities:
                entities[parent_id].children = children

        # Collect root entities. An entity is a root if it declares no parent, or
        # if its parent_id points at an entity that is not present (a dangling
        # reference): promoting the latter to root keeps it reachable rather than
        # silently dropping it from the tree.
        for entity in entities.values():
            if not entity.parent_id or entity.parent_id not in entities:
                tree.append(entity)

        return tree

    def _save(self: Self) -> None:
        """Save entities to file."""
        if not self._path:
            logger.warning("No dataset path configured, skipping save")
            return

        # Serialize tree to flat list with hierarchy metadata
        entities_data: list[dict[str, Any]] = []

        def serialize_recursive(entity: EntityData) -> None:
            entity_dict = {
                "id": entity.id,
                "entity_type": entity.entity_type,
                "label": entity.label,
                "parent_id": entity.parent_id,
                **entity.data,
            }
            entities_data.append(entity_dict)
            for child in entity.children:
                serialize_recursive(child)

        for root in self._tree:
            serialize_recursive(root)

        data = {
            "profile": self._profile,
            "version": self._version or self._get_facade().version,
            "modified": datetime.now(UTC).isoformat(),
            "entities": entities_data,
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("Saved %d entities to %s", len(self._entities), self._path)

    # EntityRepository implementation

    def list_entities(self: Self, entity_type: str | None = None) -> list[EntityData]:
        """List all entities, optionally filtered by type.

        Returns deep copies so a caller mutating a result cannot corrupt the
        repository's internal store.
        """
        return [
            copy.deepcopy(e)
            for e in self._entities.values()
            if entity_type is None or e.entity_type == entity_type
        ]

    def get_entity(self: Self, entity_id: str) -> EntityData | None:
        """Get a single entity by ID (a deep copy, so callers cannot mutate the store)."""
        entity = self._entities.get(entity_id)
        return copy.deepcopy(entity) if entity is not None else None

    def create_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str | None = None,
    ) -> EntityData:
        """Create a new entity."""
        facade = self._get_facade()

        # Validate entity type against the active profile's spec
        helper = facade.require_helper(entity_type)

        # Auto-detect parent from reference fields if not explicitly provided
        if not parent_id:
            parent_id = self._find_parent_from_references(helper, data)

        # Validate parent
        parent = None
        if parent_id:
            parent = self._entities.get(parent_id)
            if not parent:
                raise ValueError(f"Parent entity not found: {parent_id}")

            # Validate parent-child relationship
            parent_helper = getattr(facade, parent.entity_type, None)
            if parent_helper:
                valid_child_types = list(parent_helper.child_fields.values())
                if entity_type not in valid_child_types:
                    raise ValueError(
                        f"Invalid parent: {parent.entity_type} cannot contain "
                        f"{entity_type}. Valid child types: "
                        f"{valid_child_types or 'none'}"
                    )

            # Auto-fill child's reference to parent
            ref_field = find_parent_ref_field(helper, parent.entity_type)
            if ref_field and ref_field not in data and parent_helper:
                parent_identifier = get_identifier(parent.data, parent_helper)
                if parent_identifier:
                    data[ref_field] = parent_identifier

        # Normalize reference fields (convert embedded objects to IDs)
        data = normalize_reference_fields(data, helper, facade)

        # Create Pydantic instance for validation
        instance = helper.create(**data)
        validated_data = instance.model_dump(exclude_none=True)

        # Create entity
        entity = EntityData(
            id=str(uuid.uuid4())[:8],
            entity_type=entity_type,
            label=derive_label(entity_type, validated_data, spec=helper._spec),
            data=validated_data,
            parent_id=parent_id,
        )

        # Add to structures
        self._entities[entity.id] = entity

        if parent:
            parent.children.append(entity)
            # Update parent's nested reference
            update_parent_reference(
                facade,
                parent.data,
                parent.entity_type,
                entity.data,
                entity.entity_type,
                entity.id,
            )
        else:
            self._tree.append(entity)

        self._save()
        # A copy, like every read path: the internal object persisted by the
        # next _save must not be reachable from outside.
        return copy.deepcopy(entity)

    def update_entity(self: Self, entity_id: str, data: dict[str, Any]) -> EntityData:
        """Update an existing entity."""
        entity = self._entities.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        facade = self._get_facade()
        helper = getattr(facade, entity.entity_type, None)
        if not helper:
            raise ValueError(f"Unknown entity type: {entity.entity_type}")

        # Normalize reference fields (convert embedded objects to IDs)
        data = normalize_reference_fields(data, helper, facade)

        # Merge data
        merged = {**entity.data, **data}

        # Validate via Pydantic
        instance = helper.create(**merged)
        validated_data = instance.model_dump(exclude_none=True)

        # Update entity
        entity.data = validated_data
        entity.label = derive_label(
            entity.entity_type, validated_data, spec=helper._spec
        )

        self._save()
        # A copy, like every read path: the internal object persisted by the
        # next _save must not be reachable from outside.
        return copy.deepcopy(entity)

    def _find_parent_from_references(
        self: Self, helper: Any, data: dict[str, Any]
    ) -> str | None:
        """Auto-detect a parent from the entity's reference fields.

        Mirrors the memory backend: for each reference field present in the
        data, find an existing entity of the referenced type whose target
        field matches the reference value.

        Args:
            helper: EntityHelper for the entity being created.
            data: Entity data containing potential reference values.

        Returns:
            The matching parent entity id, or None if no match is found.
        """
        for field_name, (target_type, target_field) in helper.reference_fields.items():
            ref_value = data.get(field_name)
            if not ref_value:
                continue

            for entity in self._entities.values():
                if entity.entity_type != target_type:
                    continue
                if entity.data.get(target_field) == ref_value:
                    return entity.id

        return None

    def delete_entity(self: Self, entity_id: str) -> bool:
        """Delete an entity and its children."""
        entity = self._entities.get(entity_id)
        if not entity:
            return False

        # Recursively delete children
        def delete_recursive(e: EntityData) -> None:
            for child in e.children:
                delete_recursive(child)
            self._entities.pop(e.id, None)

        delete_recursive(entity)

        # Remove from parent or tree
        if entity.parent_id and entity.parent_id in self._entities:
            parent = self._entities[entity.parent_id]
            parent.children = [c for c in parent.children if c.id != entity_id]
            # Take the reference back out of the parent's data — create put
            # it there, and a dangling identifier survives save and export.
            remove_parent_reference(
                self._get_facade(),
                parent.data,
                parent.entity_type,
                entity.data,
                entity.entity_type,
                entity.id,
            )
        else:
            self._tree = [e for e in self._tree if e.id != entity_id]

        self._save()
        return True

    def get_tree(self: Self) -> list[EntityData]:
        """Get the full entity tree with nested children (deep copies)."""
        return copy.deepcopy(self._tree)

    def get_profile(self: Self) -> str:
        """Get the current profile name."""
        return self._profile

    def get_version(self: Self) -> str | None:
        """Get the current profile version."""
        return self._version

    def set_profile(self: Self, profile: str, version: str | None = None) -> None:
        """Set the active profile and version."""
        self._profile = profile
        self._version = version
        self._facade = None  # Force reload

    def reload(self: Self) -> None:
        """Reload data from file.

        Call this to sync with external changes (e.g., from MCP).
        """
        self._load()
