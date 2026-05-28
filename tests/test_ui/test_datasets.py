"""Tests for dataset persistence."""

import json
from unittest.mock import patch

import pytest

from metaseed.repositories.dataset_repository import DatasetRepository
from metaseed.ui.datasets import (
    delete_dataset,
    list_datasets,
    load_dataset,
    save_dataset,
    validate_dataset_name,
)
from metaseed.ui.state import AppState


@pytest.fixture
def temp_datasets_dir(tmp_path):
    """Use a temporary directory for datasets."""
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    with (
        patch("metaseed.repositories.filesystem_dataset.DEFAULT_DATASETS_DIR", datasets_dir),
        patch("metaseed.ui.datasets.DATASETS_DIR", datasets_dir),
        # Reset the module-level factory so it picks up the new directory
        patch("metaseed.ui.datasets._factory", None),
    ):
        yield datasets_dir


class TestValidateDatasetName:
    """Tests for dataset name validation."""

    def test_valid_names(self):
        """Valid names should pass."""
        assert validate_dataset_name("my-dataset") is None
        assert validate_dataset_name("dataset_123") is None
        assert validate_dataset_name("MyDataset") is None
        assert validate_dataset_name("a") is None

    def test_empty_name(self):
        """Empty name should fail."""
        assert validate_dataset_name("") is not None
        assert DatasetRepository.validate_name("   ") is not None

    def test_invalid_start_char(self):
        """Name starting with invalid char should fail."""
        assert validate_dataset_name("-dataset") is not None
        assert validate_dataset_name("_dataset") is not None
        # Numbers at start are allowed
        assert validate_dataset_name("123dataset") is None

    def test_invalid_chars(self):
        """Name with invalid chars should fail."""
        assert validate_dataset_name("my dataset") is not None
        assert validate_dataset_name("my.dataset") is not None
        assert validate_dataset_name("my/dataset") is not None

    def test_too_long(self):
        """Name over 64 chars should fail."""
        assert validate_dataset_name("a" * 65) is not None
        assert validate_dataset_name("a" * 64) is None


class TestListDatasets:
    """Tests for listing datasets."""

    def test_empty_directory(self, temp_datasets_dir):
        """Empty directory should return empty list."""
        result = list_datasets()
        assert result == []

    def test_lists_datasets(self, temp_datasets_dir):
        """Should list saved datasets."""
        # Create test dataset files
        (temp_datasets_dir / "test1.json").write_text(
            json.dumps(
                {
                    "name": "test1",
                    "profile": "miappe",
                    "version": "1.2",
                    "entities": [{"_type": "Investigation"}],
                    "modified": "2024-01-01T00:00:00",
                }
            )
        )
        (temp_datasets_dir / "test2.json").write_text(
            json.dumps(
                {
                    "name": "test2",
                    "profile": "isa",
                    "version": "1.0",
                    "entities": [],
                    "modified": "2024-01-02T00:00:00",
                }
            )
        )

        result = list_datasets()
        assert len(result) == 2

        # Should be sorted by modified time, most recent first
        names = [d["name"] for d in result]
        assert "test1" in names
        assert "test2" in names

    def test_skips_invalid_files(self, temp_datasets_dir):
        """Should skip invalid JSON files."""
        (temp_datasets_dir / "valid.json").write_text(
            json.dumps({"name": "valid", "profile": "miappe", "version": "1.0", "entities": []})
        )
        (temp_datasets_dir / "invalid.json").write_text("not json")

        result = list_datasets()
        assert len(result) == 1
        assert result[0]["name"] == "valid"


class TestSaveDataset:
    """Tests for saving datasets."""

    def test_save_empty_state(self, temp_datasets_dir):
        """Should save empty state."""
        state = AppState(profile="miappe")

        result = save_dataset(state, "test-dataset")

        assert result["name"] == "test-dataset"
        assert result["profile"] == "miappe"
        assert result["entity_count"] == 0

        # Verify file was created
        path = temp_datasets_dir / "test-dataset.json"
        assert path.exists()

    def test_save_with_entities(self, temp_datasets_dir):
        """Should save state with entities."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()

        # Create an investigation
        inv = facade.Investigation.create(
            unique_id="INV-001",
            title="Test Investigation",
        )
        state.add_node("Investigation", inv)

        result = save_dataset(state, "with-entities")

        assert result["entity_count"] == 1

        # Verify content
        path = temp_datasets_dir / "with-entities.json"
        data = json.loads(path.read_text())
        assert len(data["entities"]) == 1
        assert data["entities"][0]["_type"] == "Investigation"
        assert data["entities"][0]["unique_id"] == "INV-001"

    def test_save_invalid_name(self, temp_datasets_dir):
        """Should reject invalid names."""
        state = AppState(profile="miappe")

        with pytest.raises(ValueError):
            save_dataset(state, "")

        with pytest.raises(ValueError):
            save_dataset(state, "invalid name")


class TestLoadDataset:
    """Tests for loading datasets."""

    def test_load_dataset(self, temp_datasets_dir):
        """Should load dataset into state."""
        # Create dataset file
        (temp_datasets_dir / "mydata.json").write_text(
            json.dumps(
                {
                    "name": "mydata",
                    "profile": "miappe",
                    "version": "1.2",
                    "entities": [
                        {
                            "_type": "Investigation",
                            "unique_id": "INV-001",
                            "title": "Test Investigation",
                        }
                    ],
                }
            )
        )

        state = AppState(profile="isa")  # Different initial profile
        result = load_dataset(state, "mydata")

        assert result["name"] == "mydata"
        assert result["entity_count"] == 1
        assert state.profile == "miappe"
        assert len(state.entity_tree) == 1

    def test_load_nonexistent(self, temp_datasets_dir):
        """Should raise error for nonexistent dataset."""
        state = AppState()

        with pytest.raises(FileNotFoundError):
            load_dataset(state, "nonexistent")


class TestDeleteDataset:
    """Tests for deleting datasets."""

    def test_delete_existing(self, temp_datasets_dir):
        """Should delete existing dataset."""
        path = temp_datasets_dir / "todelete.json"
        path.write_text(json.dumps({"name": "todelete"}))

        assert delete_dataset("todelete") is True
        assert not path.exists()

    def test_delete_nonexistent(self, temp_datasets_dir):
        """Should return False for nonexistent."""
        assert delete_dataset("nonexistent") is False
