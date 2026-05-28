"""Tests for DatasetManager and DatasetManagerFactory."""

from unittest.mock import MagicMock, patch

import pytest

from metaseed.repositories.dataset_repository import DatasetData, DatasetInfo, DatasetRepository
from metaseed.ui.dataset_manager import (
    DatasetManager,
    DatasetManagerFactory,
)
from metaseed.ui.state import AppState


class MockDatasetRepository(DatasetRepository):
    """Mock repository for testing."""

    def __init__(self):
        self.datasets: dict[str, DatasetData] = {}

    def list(self) -> list[DatasetInfo]:
        return [
            DatasetInfo(
                name=name,
                profile=data.profile,
                version=data.version,
                entity_count=len(data.entities),
                modified=data.modified,
            )
            for name, data in self.datasets.items()
        ]

    def save(self, name: str, data: DatasetData) -> DatasetInfo:
        error = self.validate_name(name)
        if error:
            raise ValueError(error)
        self.datasets[name] = data
        return DatasetInfo(
            name=name,
            profile=data.profile,
            version=data.version,
            entity_count=len(data.entities),
            modified=data.modified,
        )

    def load(self, name: str) -> DatasetData:
        if name not in self.datasets:
            raise FileNotFoundError(f"Dataset not found: {name}")
        return self.datasets[name]

    def delete(self, name: str) -> bool:
        if name in self.datasets:
            del self.datasets[name]
            return True
        return False

    def exists(self, name: str) -> bool:
        return name in self.datasets


class TestDatasetManager:
    """Tests for DatasetManager class."""

    @pytest.fixture
    def manager(self):
        """Create manager with mock repository."""
        repo = MockDatasetRepository()
        state = AppState(profile="miappe")
        return DatasetManager(repo, state)

    def test_list_datasets_empty(self, manager):
        """Should return empty list initially."""
        result = manager.list_datasets()
        assert result == []

    def test_save_dataset(self, manager):
        """Should save current state."""
        result = manager.save_dataset("test")

        assert result.name == "test"
        assert result.profile == "miappe"
        assert manager.current_dataset == "test"

    def test_save_with_entities(self, manager):
        """Should save state with entities."""
        facade = manager._state.get_or_create_facade()
        inv = facade.Investigation.create(
            unique_id="INV-001",
            title="Test Investigation",
        )
        manager._state.add_node("Investigation", inv)

        result = manager.save_dataset("with-entities")

        assert result.entity_count == 1

    def test_save_invalid_name(self, manager):
        """Should reject invalid names."""
        with pytest.raises(ValueError):
            manager.save_dataset("")

        with pytest.raises(ValueError):
            manager.save_dataset("invalid name")

    def test_load_dataset(self, manager):
        """Should load dataset into state."""
        # Save first
        manager.save_dataset("test")

        # Create a new state/manager to load into
        new_state = AppState(profile="isa")
        new_manager = DatasetManager(manager._repo, new_state)

        result = new_manager.load_dataset("test")

        assert result.name == "test"
        assert new_manager.current_dataset == "test"
        assert new_state.profile == "miappe"

    def test_load_nonexistent(self, manager):
        """Should raise error for nonexistent dataset."""
        with pytest.raises(FileNotFoundError):
            manager.load_dataset("nonexistent")

    def test_delete_dataset(self, manager):
        """Should delete dataset."""
        manager.save_dataset("todelete")
        assert manager.dataset_exists("todelete")

        result = manager.delete_dataset("todelete")

        assert result is True
        assert not manager.dataset_exists("todelete")

    def test_delete_current_clears_name(self, manager):
        """Deleting current dataset should clear current_dataset."""
        manager.save_dataset("current")
        assert manager.current_dataset == "current"

        manager.delete_dataset("current")

        assert manager.current_dataset is None

    def test_delete_nonexistent(self, manager):
        """Should return False for nonexistent."""
        result = manager.delete_dataset("nonexistent")
        assert result is False

    def test_dataset_exists(self, manager):
        """Should check existence correctly."""
        assert not manager.dataset_exists("test")

        manager.save_dataset("test")

        assert manager.dataset_exists("test")

    def test_current_dataset_property(self, manager):
        """Should track current dataset."""
        assert manager.current_dataset is None

        manager.save_dataset("first")
        assert manager.current_dataset == "first"

        manager.current_dataset = "second"
        assert manager.current_dataset == "second"

        manager.current_dataset = None
        assert manager.current_dataset is None


class TestDatasetManagerFactory:
    """Tests for DatasetManagerFactory class."""

    def test_factory_creates_manager(self):
        """Factory should create manager for state."""
        factory = DatasetManagerFactory()
        state = AppState(profile="miappe")

        manager = factory.get_manager(state)

        assert isinstance(manager, DatasetManager)
        assert manager._state is state

    def test_factory_uses_custom_repository(self):
        """Factory should use custom repository."""
        custom_repo = MockDatasetRepository()
        factory = DatasetManagerFactory(sync_repo=custom_repo)
        state = AppState(profile="miappe")

        manager = factory.get_manager(state)

        assert manager.repository is custom_repo

    def test_factory_reuses_manager_for_same_state(self):
        """Factory should return same manager for same state."""
        factory = DatasetManagerFactory()
        state = AppState(profile="miappe")

        manager1 = factory.get_manager(state)
        manager2 = factory.get_manager(state)

        assert manager1 is manager2

    def test_factory_creates_new_manager_for_different_state(self):
        """Factory should create new manager for different state."""
        factory = DatasetManagerFactory()
        state1 = AppState(profile="miappe")
        state2 = AppState(profile="isa")

        manager1 = factory.get_manager(state1)
        manager2 = factory.get_manager(state2)

        assert manager1 is not manager2

    def test_factory_default_repository(self):
        """Factory should use FilesystemDatasetRepository by default."""
        with patch("metaseed.ui.dataset_manager.FilesystemDatasetRepository") as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo

            factory = DatasetManagerFactory()
            state = AppState(profile="miappe")
            manager = factory.get_manager(state)

            assert manager.repository is mock_repo

    def test_sync_repo_property(self):
        """Factory should expose sync_repo property."""
        custom_repo = MockDatasetRepository()
        factory = DatasetManagerFactory(sync_repo=custom_repo)

        assert factory.sync_repo is custom_repo

    def test_async_repo_property(self):
        """Factory should expose async_repo property."""
        factory = DatasetManagerFactory()

        assert factory.async_repo is None
