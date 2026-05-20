"""Dataset manager with dependency injection support.

Provides a central interface for dataset operations that integrates
with AppState and allows repository implementation to be swapped
(e.g., for metaseed-hub database backend).
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from metaseed.repositories.dataset_repository import DatasetData, DatasetInfo, DatasetRepository
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

        facade = self._state.get_or_create_facade()

        entities: list[dict[str, Any]] = []
        for node in self._state.entity_tree:
            entities.extend(serialize_tree_node(node))

        data = DatasetData(
            name=name,
            profile=self._state.profile,
            version=self._state.version or facade.version,
            entities=entities,
            modified=datetime.now().isoformat(),
        )

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

        self._state.profile = data.profile
        self._state.version = data.version
        self._state.facade = None
        self._state.reset()

        facade = self._state.get_or_create_facade()
        loaded_count = 0

        unique_id_to_node: dict[str, Any] = {}
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

                    fields = {k: v for k, v in entity_data.items() if not k.startswith("_")}
                    instance = helper.create(**fields)

                    node = self._state.add_node(entity_type, instance)
                    loaded_count += 1

                    entity_unique_id = fields.get("unique_id")
                    if entity_unique_id:
                        unique_id_to_node[entity_unique_id] = node

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
                parent_node = unique_id_to_node.get(parent_ref)
            else:
                parent_node = old_id_to_node.get(parent_ref)

            if parent_node:
                self._state.entity_tree = [n for n in self._state.entity_tree if n.id != node.id]
                node.parent_id = parent_node.id
                parent_node.children.append(node)

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


_default_manager: DatasetManager | None = None
_repository: DatasetRepository | None = None


def set_repository(repo: DatasetRepository) -> None:
    """Set the repository for dataset operations.

    Call this before app startup to use a custom repository
    (e.g., database-backed for metaseed-hub).

    Args:
        repo: DatasetRepository implementation to use.
    """
    global _repository, _default_manager
    _repository = repo
    _default_manager = None


def get_repository() -> DatasetRepository:
    """Get the configured repository.

    Returns:
        The configured repository, or FilesystemDatasetRepository as default.
    """
    global _repository
    if _repository is None:
        _repository = FilesystemDatasetRepository()
    return _repository


def get_manager(state: AppState) -> DatasetManager:
    """Get or create the dataset manager.

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


def reset_manager() -> None:
    """Reset the module-level manager.

    Useful for testing or when switching repositories.
    """
    global _default_manager, _repository
    _default_manager = None
    _repository = None


def list_datasets_compat() -> list[dict[str, Any]]:
    """List datasets (backward-compatible dict format).

    Returns:
        List of dataset info dicts.
    """
    repo = get_repository()
    return [asdict(d) for d in repo.list()]
