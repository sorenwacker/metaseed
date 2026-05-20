"""Tests for DatasetManager."""

from unittest.mock import MagicMock, patch

import pytest

from metaseed.repositories.dataset_repository import DatasetData, DatasetInfo, DatasetRepository
from metaseed.ui.dataset_manager import (
    DatasetManager,
    get_manager,
    reset_manager,
    set_repository,
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


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    reset_manager()
    yield
    reset_manager()


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


class TestModuleLevelFunctions:
    """Tests for module-level DI functions."""

    def test_set_repository(self):
        """set_repository should configure custom repository."""
        custom_repo = MockDatasetRepository()
        set_repository(custom_repo)

        state = AppState(profile="miappe")
        manager = get_manager(state)

        assert manager.repository is custom_repo

    def test_get_manager_creates_default(self):
        """get_manager should create FilesystemDatasetRepository by default."""
        with patch("metaseed.ui.dataset_manager.FilesystemDatasetRepository") as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo

            state = AppState(profile="miappe")
            manager = get_manager(state)

            assert manager.repository is mock_repo

    def test_get_manager_reuses_with_same_state(self):
        """get_manager should return same instance for same state."""
        state = AppState(profile="miappe")

        manager1 = get_manager(state)
        manager2 = get_manager(state)

        assert manager1 is manager2

    def test_get_manager_recreates_with_different_state(self):
        """get_manager should create new instance for different state."""
        state1 = AppState(profile="miappe")
        state2 = AppState(profile="isa")

        manager1 = get_manager(state1)
        manager2 = get_manager(state2)

        assert manager1 is not manager2

    def test_reset_manager(self):
        """reset_manager should clear module state."""
        custom_repo = MockDatasetRepository()
        set_repository(custom_repo)

        state = AppState(profile="miappe")
        manager1 = get_manager(state)

        reset_manager()

        # After reset, a new manager with default repo should be created
        with patch("metaseed.ui.dataset_manager.FilesystemDatasetRepository") as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo

            manager2 = get_manager(state)

            assert manager2 is not manager1
