"""Tests for JSON storage backend."""

import json
from pathlib import Path

import pytest

from miappe_api.models import get_model
from miappe_api.storage.json_backend import JsonStorage


class TestJsonStorage:
    """Tests for JsonStorage class."""

    @pytest.fixture
    def storage(self) -> JsonStorage:
        """Create a JSON storage instance."""
        return JsonStorage()

    @pytest.fixture
    def investigation_model(self):
        """Get Investigation model."""
        return get_model("Investigation", version="1.1")

    @pytest.fixture
    def sample_investigation(self, investigation_model):
        """Create a sample investigation instance."""
        return investigation_model(
            unique_id="INV001",
            title="Test Investigation",
            description="A test investigation for storage testing",
        )

    def test_save_to_file(
        self,
        storage: JsonStorage,
        sample_investigation,
        tmp_path: Path,
    ) -> None:
        """Save entity to JSON file."""
        file_path = tmp_path / "investigation.json"
        storage.save(sample_investigation, file_path)

        assert file_path.exists()
        content = file_path.read_text()
        data = json.loads(content)
        assert data["unique_id"] == "INV001"
        assert data["title"] == "Test Investigation"

    def test_load_from_file(
        self,
        storage: JsonStorage,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Load entity from JSON file."""
        file_path = tmp_path / "investigation.json"
        data = {
            "unique_id": "INV002",
            "title": "Loaded Investigation",
        }
        file_path.write_text(json.dumps(data))

        loaded = storage.load(file_path, investigation_model)

        assert loaded.unique_id == "INV002"
        assert loaded.title == "Loaded Investigation"

    def test_round_trip(
        self,
        storage: JsonStorage,
        sample_investigation,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Save and load maintains data integrity."""
        file_path = tmp_path / "investigation.json"

        storage.save(sample_investigation, file_path)
        loaded = storage.load(file_path, investigation_model)

        assert loaded.unique_id == sample_investigation.unique_id
        assert loaded.title == sample_investigation.title
        assert loaded.description == sample_investigation.description

    def test_save_creates_parent_dirs(
        self,
        storage: JsonStorage,
        sample_investigation,
        tmp_path: Path,
    ) -> None:
        """Save creates parent directories if needed."""
        file_path = tmp_path / "subdir" / "nested" / "investigation.json"
        storage.save(sample_investigation, file_path)

        assert file_path.exists()

    def test_load_nonexistent_raises(
        self,
        storage: JsonStorage,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Loading nonexistent file raises error."""
        from miappe_api.storage.base import StorageError

        file_path = tmp_path / "nonexistent.json"
        with pytest.raises(StorageError):
            storage.load(file_path, investigation_model)

    def test_load_invalid_json_raises(
        self,
        storage: JsonStorage,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Loading invalid JSON raises error."""
        from miappe_api.storage.base import StorageError

        file_path = tmp_path / "invalid.json"
        file_path.write_text("not valid json {")
        with pytest.raises(StorageError):
            storage.load(file_path, investigation_model)

    def test_save_with_pretty_print(
        self,
        storage: JsonStorage,
        sample_investigation,
        tmp_path: Path,
    ) -> None:
        """Save with indent produces formatted JSON."""
        storage = JsonStorage(indent=2)
        file_path = tmp_path / "pretty.json"
        storage.save(sample_investigation, file_path)

        content = file_path.read_text()
        assert "\n" in content  # Pretty printed has newlines
        assert "  " in content  # Has indentation


class TestJsonStorageWithNested:
    """Tests for nested entity storage."""

    def test_save_with_list_field(self, tmp_path: Path) -> None:
        """Save entity with list field."""
        storage = JsonStorage()
        Model = get_model("Investigation", version="1.1")

        inv = Model(
            unique_id="INV003",
            title="Investigation with Publications",
            associated_publications=["doi:10.1234/test1", "doi:10.1234/test2"],
        )
        file_path = tmp_path / "inv_with_list.json"
        storage.save(inv, file_path)

        loaded = storage.load(file_path, Model)
        assert loaded.associated_publications == ["doi:10.1234/test1", "doi:10.1234/test2"]
