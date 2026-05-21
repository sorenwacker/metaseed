"""Dataset manager with dependency injection support.

Provides a central interface for dataset operations that integrates
with AppState and allows repository implementation to be swapped
(e.g., for metaseed-hub database backend).

Two managers are provided:
- DatasetManager: Synchronous manager (for filesystem, simple use cases)
- AsyncDatasetManager: Asynchronous manager (for database backends)
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from metaseed.repositories.dataset_repository import (
    AsyncDatasetRepository,
    DatasetData,
    DatasetInfo,
    DatasetRepository,
)
from metaseed.repositories.filesystem_dataset import (
    FilesystemDatasetRepository,
    serialize_tree_node,
)

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


class DatasetManager:
    """Manages dataset operations with DI support.

    Integrates a DatasetRepository with AppState to provide
    high-level dataset operations including state synchronization.
    """

    def __init__(
        self,
        repository: DatasetRepository,
        state: AppState,
    ):
        """Initialize dataset manager.

        Args:
            repository: DatasetRepository implementation for storage.
            state: AppState instance for entity management.
        """
        self._repo = repository
        self._state = state
        self._current: str | None = None

    @property
    def repository(self) -> DatasetRepository:
        """Get the underlying repository."""
        return self._repo

    @property
    def current_dataset(self) -> str | None:
        """Get the name of the currently loaded dataset."""
        return self._current

    @current_dataset.setter
    def current_dataset(self, name: str | None) -> None:
        """Set the current dataset name."""
        self._current = name

    def list_datasets(self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries.
        """
        return self._repo.list()

    def save_dataset(self, name: str) -> DatasetInfo:
        """Save current state as a named dataset.

        Args:
            name: Dataset name.

        Returns:
            DatasetInfo for the saved dataset.

        Raises:
            ValueError: If name is invalid.
        """
        error = DatasetRepository.validate_name(name)
        if error:
            raise ValueError(error)

        data = self._build_dataset_data(name)
        result = self._repo.save(name, data)
        self._current = name
        return result

    def load_dataset(self, name: str) -> DatasetInfo:
        """Load a dataset into the state.

        Args:
            name: Dataset name to load.

        Returns:
            DatasetInfo for the loaded dataset.

        Raises:
            FileNotFoundError: If dataset doesn't exist.
        """
        data = self._repo.load(name)
        loaded_count = self._restore_state_from_data(data)
        self._current = name

        return DatasetInfo(
            name=name,
            profile=data.profile,
            version=data.version,
            entity_count=loaded_count,
            modified=data.modified,
        )

    def delete_dataset(self, name: str) -> bool:
        """Delete a dataset.

        Args:
            name: Dataset name to delete.

        Returns:
            True if deleted, False if not found.
        """
        result = self._repo.delete(name)
        if result and self._current == name:
            self._current = None
        return result

    def dataset_exists(self, name: str) -> bool:
        """Check if a dataset exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        return self._repo.exists(name)

    def auto_save(self) -> None:
        """Auto-save the current state.

        Saves to the current dataset if one is loaded, otherwise derives
        a name from the first entity's label.
        """
        name = self._current or self._get_default_dataset_name()

        try:
            result = self.save_dataset(name)

            from metaseed.ui.websocket import notify_state_changed

            notify_state_changed(
                event="state_changed",
                dataset=name,
                entity_count=result.entity_count,
            )
        except (ValueError, OSError):
            pass

    def _get_default_dataset_name(self) -> str:
        """Get a default dataset name from the first entity's label."""
        if self._state.entity_tree:
            label = self._state.entity_tree[0].label
            if label and label != f"New {self._state.entity_tree[0].entity_type}":
                name = re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-").lower()
                if name and len(name) <= 64:
                    return name
        return "autosave"

    def _build_dataset_data(self, name: str) -> DatasetData:
        """Build DatasetData from current state."""
        facade = self._state.get_or_create_facade()

        entities: list[dict[str, Any]] = []
        for node in self._state.entity_tree:
            entities.extend(serialize_tree_node(node))

        return DatasetData(
            name=name,
            profile=self._state.profile,
            version=self._state.version or facade.version,
            entities=entities,
            modified=datetime.now().isoformat(),
        )

    def _restore_state_from_data(self, data: DatasetData) -> int:
        """Restore state from DatasetData, returns loaded count."""
        self._state.profile = data.profile
        self._state.version = data.version
        self._state.facade = None
        self._state.reset()

        facade = self._state.get_or_create_facade()
        loaded_count = 0

        id_to_node: dict[str, Any] = {}  # unique_id or alias -> node
        old_id_to_node: dict[str, Any] = {}
        nodes_with_parent: list[tuple[Any, str, bool]] = []

        for entity_data in data.entities:
            entity_type = entity_data.get("_type")
            if not entity_type:
                continue

            try:
                helper = getattr(facade, entity_type, None)
                if helper:
                    parent_unique_id = entity_data.get("_parent_unique_id")
                    old_parent_id = entity_data.get("_parent_id")
                    old_node_id = entity_data.get("_node_id")

                    # Lenient loading: filter to only fields defined in schema
                    valid_fields = set(helper.all_fields)
                    fields = {
                        k: v
                        for k, v in entity_data.items()
                        if not k.startswith("_") and k in valid_fields
                    }
                    instance = helper.create(**fields)

                    node = self._state.add_node(entity_type, instance)
                    loaded_count += 1

                    # Index by unique_id or alias for parent lookup
                    entity_id = fields.get("unique_id") or fields.get("alias")
                    if entity_id:
                        id_to_node[entity_id] = node

                    if old_node_id:
                        old_id_to_node[old_node_id] = node

                    if parent_unique_id:
                        nodes_with_parent.append((node, parent_unique_id, True))
                    elif old_parent_id:
                        nodes_with_parent.append((node, old_parent_id, False))
            except Exception:  # noqa: S112
                continue

        for node, parent_ref, is_unique_id in nodes_with_parent:
            if is_unique_id:
                parent_node = id_to_node.get(parent_ref)
            else:
                parent_node = old_id_to_node.get(parent_ref)

            if parent_node:
                self._state.entity_tree = [n for n in self._state.entity_tree if n.id != node.id]
                node.parent_id = parent_node.id
                parent_node.children.append(node)

        # Link children via parent's nested arrays (e.g., Study.samples contains child aliases)
        for node in list(self._state.entity_tree):
            if node.parent_id:
                continue  # Already linked

            helper = getattr(facade, node.entity_type, None)
            if not helper:
                continue

            node_data = node.instance.model_dump() if node.instance else {}

            # Check nested fields (e.g., Study.samples, Study.experiments)
            for field_name in helper.nested_fields:
                child_ids = node_data.get(field_name, [])
                if not isinstance(child_ids, list):
                    continue

                for child_id in child_ids:
                    child_node = id_to_node.get(child_id)
                    if child_node and child_node.parent_id is None:
                        # Link child to this parent
                        self._state.entity_tree = [
                            n for n in self._state.entity_tree if n.id != child_node.id
                        ]
                        child_node.parent_id = node.id
                        node.children.append(child_node)

        return loaded_count


class AsyncDatasetManager:
    """Manages dataset operations with async DI support.

    Integrates an AsyncDatasetRepository with AppState to provide
    high-level async dataset operations for database backends.
    """

    def __init__(
        self,
        repository: AsyncDatasetRepository,
        state: AppState,
    ):
        """Initialize async dataset manager.

        Args:
            repository: AsyncDatasetRepository implementation for storage.
            state: AppState instance for entity management.
        """
        self._repo = repository
        self._state = state
        self._current: str | None = None

    @property
    def repository(self) -> AsyncDatasetRepository:
        """Get the underlying repository."""
        return self._repo

    @property
    def current_dataset(self) -> str | None:
        """Get the name of the currently loaded dataset."""
        return self._current

    @current_dataset.setter
    def current_dataset(self, name: str | None) -> None:
        """Set the current dataset name."""
        self._current = name

    async def list_datasets(self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries.
        """
        return await self._repo.list()

    async def save_dataset(self, name: str) -> DatasetInfo:
        """Save current state as a named dataset.

        Args:
            name: Dataset name.

        Returns:
            DatasetInfo for the saved dataset.

        Raises:
            ValueError: If name is invalid.
        """
        error = AsyncDatasetRepository.validate_name(name)
        if error:
            raise ValueError(error)

        data = self._build_dataset_data(name)
        result = await self._repo.save(name, data)
        self._current = name
        return result

    async def load_dataset(self, name: str) -> DatasetInfo:
        """Load a dataset into the state.

        Args:
            name: Dataset name to load.

        Returns:
            DatasetInfo for the loaded dataset.

        Raises:
            FileNotFoundError: If dataset doesn't exist.
        """
        data = await self._repo.load(name)
        loaded_count = self._restore_state_from_data(data)
        self._current = name

        return DatasetInfo(
            name=name,
            profile=data.profile,
            version=data.version,
            entity_count=loaded_count,
            modified=data.modified,
        )

    async def delete_dataset(self, name: str) -> bool:
        """Delete a dataset.

        Args:
            name: Dataset name to delete.

        Returns:
            True if deleted, False if not found.
        """
        result = await self._repo.delete(name)
        if result and self._current == name:
            self._current = None
        return result

    async def dataset_exists(self, name: str) -> bool:
        """Check if a dataset exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        return await self._repo.exists(name)

    async def auto_save(self) -> None:
        """Auto-save the current state.

        Saves to the current dataset if one is loaded, otherwise derives
        a name from the first entity's label.
        """
        name = self._current or self._get_default_dataset_name()

        try:
            result = await self.save_dataset(name)

            from metaseed.ui.websocket import notify_state_changed

            notify_state_changed(
                event="state_changed",
                dataset=name,
                entity_count=result.entity_count,
            )
        except (ValueError, OSError):
            pass

    def _get_default_dataset_name(self) -> str:
        """Get a default dataset name from the first entity's label."""
        if self._state.entity_tree:
            label = self._state.entity_tree[0].label
            if label and label != f"New {self._state.entity_tree[0].entity_type}":
                name = re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-").lower()
                if name and len(name) <= 64:
                    return name
        return "autosave"

    def _build_dataset_data(self, name: str) -> DatasetData:
        """Build DatasetData from current state."""
        facade = self._state.get_or_create_facade()

        entities: list[dict[str, Any]] = []
        for node in self._state.entity_tree:
            entities.extend(serialize_tree_node(node))

        return DatasetData(
            name=name,
            profile=self._state.profile,
            version=self._state.version or facade.version,
            entities=entities,
            modified=datetime.now().isoformat(),
        )

    def _restore_state_from_data(self, data: DatasetData) -> int:
        """Restore state from DatasetData, returns loaded count."""
        self._state.profile = data.profile
        self._state.version = data.version
        self._state.facade = None
        self._state.reset()

        facade = self._state.get_or_create_facade()
        loaded_count = 0

        id_to_node: dict[str, Any] = {}  # unique_id or alias -> node
        old_id_to_node: dict[str, Any] = {}
        nodes_with_parent: list[tuple[Any, str, bool]] = []

        for entity_data in data.entities:
            entity_type = entity_data.get("_type")
            if not entity_type:
                continue

            try:
                helper = getattr(facade, entity_type, None)
                if helper:
                    parent_unique_id = entity_data.get("_parent_unique_id")
                    old_parent_id = entity_data.get("_parent_id")
                    old_node_id = entity_data.get("_node_id")

                    # Lenient loading: filter to only fields defined in schema
                    valid_fields = set(helper.all_fields)
                    fields = {
                        k: v
                        for k, v in entity_data.items()
                        if not k.startswith("_") and k in valid_fields
                    }
                    instance = helper.create(**fields)

                    node = self._state.add_node(entity_type, instance)
                    loaded_count += 1

                    # Index by unique_id or alias for parent lookup
                    entity_id = fields.get("unique_id") or fields.get("alias")
                    if entity_id:
                        id_to_node[entity_id] = node

                    if old_node_id:
                        old_id_to_node[old_node_id] = node

                    if parent_unique_id:
                        nodes_with_parent.append((node, parent_unique_id, True))
                    elif old_parent_id:
                        nodes_with_parent.append((node, old_parent_id, False))
            except Exception:  # noqa: S112
                continue

        for node, parent_ref, is_unique_id in nodes_with_parent:
            if is_unique_id:
                parent_node = id_to_node.get(parent_ref)
            else:
                parent_node = old_id_to_node.get(parent_ref)

            if parent_node:
                self._state.entity_tree = [n for n in self._state.entity_tree if n.id != node.id]
                node.parent_id = parent_node.id
                parent_node.children.append(node)

        # Link children via parent's nested arrays (e.g., Study.samples contains child aliases)
        for node in list(self._state.entity_tree):
            if node.parent_id:
                continue  # Already linked

            helper = getattr(facade, node.entity_type, None)
            if not helper:
                continue

            node_data = node.instance.model_dump() if node.instance else {}

            # Check nested fields (e.g., Study.samples, Study.experiments)
            for field_name in helper.nested_fields:
                child_ids = node_data.get(field_name, [])
                if not isinstance(child_ids, list):
                    continue

                for child_id in child_ids:
                    child_node = id_to_node.get(child_id)
                    if child_node and child_node.parent_id is None:
                        # Link child to this parent
                        self._state.entity_tree = [
                            n for n in self._state.entity_tree if n.id != child_node.id
                        ]
                        child_node.parent_id = node.id
                        node.children.append(child_node)

        return loaded_count


_default_manager: DatasetManager | None = None
_async_manager: AsyncDatasetManager | None = None
_repository: DatasetRepository | None = None
_async_repository: AsyncDatasetRepository | None = None


def set_repository(repo: DatasetRepository) -> None:
    """Set the sync repository for dataset operations.

    Call this before app startup to use a custom repository
    (e.g., database-backed for metaseed-hub).

    Args:
        repo: DatasetRepository implementation to use.
    """
    global _repository, _default_manager
    _repository = repo
    _default_manager = None


def set_async_repository(repo: AsyncDatasetRepository) -> None:
    """Set the async repository for dataset operations.

    Call this before app startup to use an async repository
    (e.g., async SQLAlchemy for metaseed-hub).

    Args:
        repo: AsyncDatasetRepository implementation to use.
    """
    global _async_repository, _async_manager
    _async_repository = repo
    _async_manager = None


def get_repository() -> DatasetRepository:
    """Get the configured sync repository.

    Returns:
        The configured repository, or FilesystemDatasetRepository as default.
    """
    global _repository
    if _repository is None:
        _repository = FilesystemDatasetRepository()
    return _repository


def get_async_repository() -> AsyncDatasetRepository | None:
    """Get the configured async repository.

    Returns:
        The configured async repository, or None if not set.
    """
    return _async_repository


def get_manager(state: AppState) -> DatasetManager:
    """Get or create the sync dataset manager.

    Args:
        state: AppState instance to use.

    Returns:
        DatasetManager instance.
    """
    global _default_manager

    if _default_manager is None or _default_manager._state is not state:
        repo = _repository or FilesystemDatasetRepository()
        _default_manager = DatasetManager(repo, state)

    return _default_manager


def get_async_manager(state: AppState) -> AsyncDatasetManager | None:
    """Get or create the async dataset manager.

    Args:
        state: AppState instance to use.

    Returns:
        AsyncDatasetManager instance, or None if no async repository is set.
    """
    global _async_manager

    if _async_repository is None:
        return None

    if _async_manager is None or _async_manager._state is not state:
        _async_manager = AsyncDatasetManager(_async_repository, state)

    return _async_manager


def reset_manager() -> None:
    """Reset all module-level managers.

    Useful for testing or when switching repositories.
    """
    global _default_manager, _repository, _async_manager, _async_repository
    _default_manager = None
    _repository = None
    _async_manager = None
    _async_repository = None


def list_datasets_compat() -> list[dict[str, Any]]:
    """List datasets (backward-compatible dict format).

    Returns:
        List of dataset info dicts.
    """
    repo = get_repository()
    return [asdict(d) for d in repo.list()]
