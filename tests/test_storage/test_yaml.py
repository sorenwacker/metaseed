"""Tests for YAML storage backend."""

from pathlib import Path

import pytest
import yaml

from miappe_api.models import get_model
from miappe_api.storage.yaml_backend import YamlStorage


class TestYamlStorage:
    """Tests for YamlStorage class."""

    @pytest.fixture
    def storage(self) -> YamlStorage:
        """Create a YAML storage instance."""
        return YamlStorage()

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
        storage: YamlStorage,
        sample_investigation,
        tmp_path: Path,
    ) -> None:
        """Save entity to YAML file."""
        file_path = tmp_path / "investigation.yaml"
        storage.save(sample_investigation, file_path)

        assert file_path.exists()
        content = file_path.read_text()
        data = yaml.safe_load(content)
        assert data["unique_id"] == "INV001"
        assert data["title"] == "Test Investigation"

    def test_load_from_file(
        self,
        storage: YamlStorage,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Load entity from YAML file."""
        file_path = tmp_path / "investigation.yaml"
        data = {
            "unique_id": "INV002",
            "title": "Loaded Investigation",
        }
        file_path.write_text(yaml.dump(data))

        loaded = storage.load(file_path, investigation_model)

        assert loaded.unique_id == "INV002"
        assert loaded.title == "Loaded Investigation"

    def test_round_trip(
        self,
        storage: YamlStorage,
        sample_investigation,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Save and load maintains data integrity."""
        file_path = tmp_path / "investigation.yaml"

        storage.save(sample_investigation, file_path)
        loaded = storage.load(file_path, investigation_model)

        assert loaded.unique_id == sample_investigation.unique_id
        assert loaded.title == sample_investigation.title
        assert loaded.description == sample_investigation.description

    def test_yaml_is_human_readable(
        self,
        storage: YamlStorage,
        sample_investigation,
        tmp_path: Path,
    ) -> None:
        """YAML output is human-readable."""
        file_path = tmp_path / "investigation.yaml"
        storage.save(sample_investigation, file_path)

        content = file_path.read_text()
        # YAML should not have JSON brackets
        assert "{" not in content
        assert "unique_id:" in content
        assert "title:" in content

    def test_load_nonexistent_raises(
        self,
        storage: YamlStorage,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Loading nonexistent file raises error."""
        from miappe_api.storage.base import StorageError

        file_path = tmp_path / "nonexistent.yaml"
        with pytest.raises(StorageError):
            storage.load(file_path, investigation_model)

    def test_load_invalid_yaml_raises(
        self,
        storage: YamlStorage,
        investigation_model,
        tmp_path: Path,
    ) -> None:
        """Loading invalid YAML raises error."""
        from miappe_api.storage.base import StorageError

        file_path = tmp_path / "invalid.yaml"
        file_path.write_text("key: value\n  invalid indent")
        with pytest.raises(StorageError):
            storage.load(file_path, investigation_model)
