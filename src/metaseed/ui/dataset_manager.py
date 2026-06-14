"""Dataset manager with dependency injection support.

Provides a central interface for dataset operations that integrates
with AppState and allows repository implementation to be swapped
(e.g., for metaseed-hub database backend).

Two managers are provided:
- DatasetManager: Synchronous manager (for filesystem, simple use cases)
- AsyncDatasetManager: Asynchronous manager (for database backends)

Both inherit from BaseDatasetManager which contains shared logic for:
- Building dataset data from state
- Restoring state from dataset data
- Default dataset name generation

Note: Entity storage and relationship linking is now handled by ProfileFacade.
The dataset manager delegates to facade.load_from_dict() and facade.to_dict()
for loading and saving operations.
"""

from __future__ import annotations

import re
from abc import ABC
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar
from weakref import WeakValueDictionary

from metaseed.repositories.dataset_repository import (
    AsyncDatasetRepository,
    DatasetData,
    DatasetInfo,
    DatasetRepository,
)
from metaseed.repositories.filesystem_dataset import (
    FilesystemDatasetRepository,
)

if TYPE_CHECKING:
    from metaseed.ui.state import AppState

# Type variable for repository type (sync or async)
R = TypeVar("R", DatasetRepository, AsyncDatasetRepository)


class BaseDatasetManager(ABC, Generic[R]):
    """Base class with shared logic for dataset managers.

    Contains common implementation for building dataset data,
    restoring state, and generating default names. Subclasses
    implement sync or async versions of the repository operations.
    """

    def __init__(
        self,
        repository: R,
        state: AppState,
    ):
        """Initialize dataset manager.

        Args:
            repository: Repository implementation for storage.
            state: AppState instance for entity management.
        """
        self._repo = repository
        self._state = state
        self._current: str | None = None

    @property
    def repository(self) -> R:
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

    def _get_default_dataset_name(self: Self) -> str:
        """Get a default dataset name from the first entity's label."""
        if self._state.entity_tree:
            label = self._state.entity_tree[0].label
            if label and label != f"New {self._state.entity_tree[0].entity_type}":
                name = re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-").lower()
                if name and len(name) <= 64:
                    return name
        return "autosave"

    def _build_dataset_data(self: Self, name: str) -> DatasetData:
        """Build DatasetData from current state.

        Delegates to facade.to_dict() for entity serialization.
        """
        facade = self._state.get_or_create_facade()

        return DatasetData(
            name=name,
            profile=self._state.profile,
            version=self._state.version or facade.version,
            entities=facade.to_dict(),
            modified=datetime.now().isoformat(),
        )

    def _restore_state_from_data(self: Self, data: DatasetData) -> int:
        """Restore state from DatasetData, returns loaded count.

        Delegates to facade.load_from_dict() for entity loading and linking.
        This single method handles:
        - Parent-child relationships via _parent_id/_parent_unique_id
        - Nested array linking (e.g., Study.samples)
        - Reference field linking (e.g., File.run_ref -> Run.alias)
        """
        self._state.profile = data.profile
        self._state.version = data.version
        self._state.facade = None
        self._state.reset()

        facade = self._state.get_or_create_facade()
        loaded_count = facade.load_from_dict(data.entities)

        # Invalidate AppState cache to pick up new data
        self._state._invalidate_cache()

        return loaded_count

    def import_data(self: Self, data: DatasetData) -> DatasetInfo:
        """Restore state from in-memory dataset data, e.g. an uploaded file.

        Unlike load_dataset, the data does not originate from the repository
        and is not marked as the current saved dataset.

        Args:
            data: Parsed dataset contents to load into the state.

        Returns:
            DatasetInfo summarizing the imported dataset.
        """
        loaded_count = self._restore_state_from_data(data)
        return DatasetInfo(
            name=data.name,
            profile=data.profile,
            version=data.version,
            entity_count=loaded_count,
            modified=data.modified,
        )


class DatasetManager(BaseDatasetManager[DatasetRepository]):
    """Manages dataset operations with DI support.

    Integrates a DatasetRepository with AppState to provide
    high-level dataset operations including state synchronization.
    """

    def list_datasets(self: Self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries.
        """
        return self._repo.list()

    def save_dataset(self: Self, name: str) -> DatasetInfo:
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

    def load_dataset(self: Self, name: str) -> DatasetInfo:
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

    def delete_dataset(self: Self, name: str) -> bool:
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

    def dataset_exists(self: Self, name: str) -> bool:
        """Check if a dataset exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        return self._repo.exists(name)

    def auto_save(self: Self) -> None:
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


class AsyncDatasetManager(BaseDatasetManager[AsyncDatasetRepository]):
    """Manages dataset operations with async DI support.

    Integrates an AsyncDatasetRepository with AppState to provide
    high-level async dataset operations for database backends.
    """

    async def list_datasets(self: Self) -> list[DatasetInfo]:
        """List all saved datasets.

        Returns:
            List of DatasetInfo summaries.
        """
        return await self._repo.list()

    async def save_dataset(self: Self, name: str) -> DatasetInfo:
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

    async def load_dataset(self: Self, name: str) -> DatasetInfo:
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

    async def delete_dataset(self: Self, name: str) -> bool:
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

    async def dataset_exists(self: Self, name: str) -> bool:
        """Check if a dataset exists.

        Args:
            name: Dataset name to check.

        Returns:
            True if exists, False otherwise.
        """
        return await self._repo.exists(name)

    async def auto_save(self: Self) -> None:
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


class DatasetManagerFactory:
    """Factory for creating DatasetManager instances tied to AppState.

    Manages DatasetManager instances using WeakValueDictionary to allow
    garbage collection when AppState instances are no longer referenced.
    This avoids global state by associating each manager with its AppState.

    Usage:
        factory = DatasetManagerFactory()
        manager = factory.get_manager(state)
    """

    def __init__(
        self,
        sync_repo: DatasetRepository | None = None,
        async_repo: AsyncDatasetRepository | None = None,
    ) -> None:
        """Initialize factory with optional custom repositories.

        Args:
            sync_repo: Sync repository implementation (default: FilesystemDatasetRepository).
            async_repo: Async repository implementation (default: None).
        """
        self._sync_repo = sync_repo or FilesystemDatasetRepository()
        self._async_repo = async_repo
        self._managers: WeakValueDictionary[int, DatasetManager] = WeakValueDictionary()
        self._async_managers: WeakValueDictionary[int, AsyncDatasetManager] = (
            WeakValueDictionary()
        )

    @property
    def sync_repo(self) -> DatasetRepository:
        """Get the sync repository."""
        return self._sync_repo

    @property
    def async_repo(self) -> AsyncDatasetRepository | None:
        """Get the async repository."""
        return self._async_repo

    def get_manager(self: Self, state: AppState) -> DatasetManager:
        """Get or create a DatasetManager for the given state.

        Args:
            state: AppState instance to create manager for.

        Returns:
            DatasetManager instance tied to the state.
        """
        state_id = id(state)
        manager = self._managers.get(state_id)
        if manager is None:
            manager = DatasetManager(self._sync_repo, state)
            self._managers[state_id] = manager
        return manager

    def get_async_manager(self: Self, state: AppState) -> AsyncDatasetManager | None:
        """Get or create an AsyncDatasetManager for the given state.

        Args:
            state: AppState instance to create manager for.

        Returns:
            AsyncDatasetManager instance, or None if no async repository is set.
        """
        if self._async_repo is None:
            return None

        state_id = id(state)
        manager = self._async_managers.get(state_id)
        if manager is None:
            manager = AsyncDatasetManager(self._async_repo, state)
            self._async_managers[state_id] = manager
        return manager


def resolve_dataset_manager(app: Any, state: AppState) -> DatasetManager:
    """Resolve the DatasetManager for a request.

    Prefers the MCP-context factory when one is attached to the app so all
    operations in an MCP session share a repository; otherwise falls back to a
    freshly created default factory.

    Args:
        app: FastAPI application, read for an optional ``state.mcp_context``.
        state: AppState the manager should be tied to.

    Returns:
        A DatasetManager tied to the given state.
    """
    context = getattr(app.state, "mcp_context", None)
    if context is not None:
        return context.dataset_factory.get_manager(state)
    return DatasetManagerFactory().get_manager(state)
