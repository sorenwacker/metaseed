"""Tests for DatasetRepository and FilesystemDatasetRepository."""

import pytest

from metaseed.repositories.dataset_repository import (
    DatasetData,
    DatasetInfo,
    DatasetRepository,
)
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository


class TestDatasetRepository:
    """Tests for DatasetRepository ABC."""

    def test_validate_name_valid(self):
        """Valid names should pass validation."""
        assert DatasetRepository.validate_name("my-dataset") is None
        assert DatasetRepository.validate_name("dataset_123") is None
        assert DatasetRepository.validate_name("MyDataset") is None
        assert DatasetRepository.validate_name("a") is None
        assert DatasetRepository.validate_name("123dataset") is None

    def test_validate_name_empty(self):
        """Empty names should fail validation."""
        assert DatasetRepository.validate_name("") is not None

    def test_validate_name_invalid_start(self):
        """Names starting with invalid chars should fail."""
        assert DatasetRepository.validate_name("-dataset") is not None
        assert DatasetRepository.validate_name("_dataset") is not None

    def test_validate_name_invalid_chars(self):
        """Names with invalid chars should fail."""
        assert DatasetRepository.validate_name("my dataset") is not None
        assert DatasetRepository.validate_name("my.dataset") is not None
        assert DatasetRepository.validate_name("my/dataset") is not None

    def test_validate_name_too_long(self):
        """Names over 64 chars should fail."""
        assert DatasetRepository.validate_name("a" * 65) is not None
        assert DatasetRepository.validate_name("a" * 64) is None


class TestDatasetInfo:
    """Tests for DatasetInfo dataclass."""

    def test_create(self):
        """Should create DatasetInfo with all fields."""
        info = DatasetInfo(
            name="test",
            profile="miappe",
            version="1.2",
            entity_count=5,
            modified="2024-01-01T00:00:00",
        )
        assert info.name == "test"
        assert info.profile == "miappe"
        assert info.version == "1.2"
        assert info.entity_count == 5
        assert info.modified == "2024-01-01T00:00:00"


class TestDatasetData:
    """Tests for DatasetData dataclass."""

    def test_create_with_defaults(self):
        """Should create DatasetData with default values."""
        data = DatasetData(
            name="test",
            profile="miappe",
            version="1.2",
        )
        assert data.name == "test"
        assert data.entities == []
        assert data.modified == ""

    def test_create_with_entities(self):
        """Should create DatasetData with entities."""
        entities = [{"_type": "Investigation", "title": "Test"}]
        data = DatasetData(
            name="test",
            profile="miappe",
            version="1.2",
            entities=entities,
            modified="2024-01-01T00:00:00",
        )
        assert len(data.entities) == 1
        assert data.entities[0]["_type"] == "Investigation"


class TestFilesystemDatasetRepository:
    """Tests for FilesystemDatasetRepository."""

    @pytest.fixture
    def repo(self, tmp_path):
        """Create repository with temp directory."""
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        return FilesystemDatasetRepository(datasets_dir)

    def test_list_empty(self, repo):
        """Empty directory should return empty list."""
        result = repo.list()
        assert result == []

    def test_save_and_load(self, repo):
        """Should save and load dataset."""
        data = DatasetData(
            name="test",
            profile="miappe",
            version="1.2",
            entities=[{"_type": "Investigation", "unique_id": "INV-001"}],
            modified="2024-01-01T00:00:00",
        )

        info = repo.save("test", data)
        assert info.name == "test"
        assert info.profile == "miappe"
        assert info.entity_count == 1

        loaded = repo.load("test")
        assert loaded.name == "test"
        assert loaded.profile == "miappe"
        assert len(loaded.entities) == 1
        assert loaded.entities[0]["unique_id"] == "INV-001"

    def test_save_invalid_name(self, repo):
        """Should reject invalid names."""
        data = DatasetData(name="", profile="miappe", version="1.2")
        with pytest.raises(ValueError):
            repo.save("", data)

    def test_load_nonexistent(self, repo):
        """Should raise FileNotFoundError for nonexistent."""
        with pytest.raises(FileNotFoundError):
            repo.load("nonexistent")

    def test_delete(self, repo):
        """Should delete existing dataset."""
        data = DatasetData(name="todelete", profile="miappe", version="1.2")
        repo.save("todelete", data)

        assert repo.exists("todelete")
        assert repo.delete("todelete") is True
        assert not repo.exists("todelete")

    def test_delete_nonexistent(self, repo):
        """Should return False for nonexistent."""
        assert repo.delete("nonexistent") is False

    @pytest.mark.parametrize(
        "evil_name",
        [
            "../secret",
            "../../etc/passwd",
            "sub/../../escape",
            "/etc/passwd",
            "..",
        ],
    )
    def test_load_rejects_path_traversal(self, repo, tmp_path, evil_name):
        """load() must not read files outside the datasets directory.

        The name becomes a filename, so an unvalidated ``../secret`` (or an
        absolute path) would escape the datasets dir. Every read/delete path,
        not only save, must reject such names.
        """
        outside = tmp_path / "secret.json"
        outside.write_text('{"name": "secret", "profile": "x", "version": "1"}')

        with pytest.raises(ValueError):
            repo.load(evil_name)

    def test_delete_rejects_path_traversal(self, repo, tmp_path):
        """delete() must not unlink files outside the datasets directory."""
        victim = tmp_path / "victim.json"
        victim.write_text("{}")

        with pytest.raises(ValueError):
            repo.delete("../victim")
        assert victim.exists()  # untouched

    def test_exists_rejects_path_traversal(self, repo, tmp_path):
        """exists() must not probe files outside the datasets directory."""
        outside = tmp_path / "probe.json"
        outside.write_text("{}")

        with pytest.raises(ValueError):
            repo.exists("../probe")

    def test_exists(self, repo):
        """Should check existence correctly."""
        assert not repo.exists("test")

        data = DatasetData(name="test", profile="miappe", version="1.2")
        repo.save("test", data)

        assert repo.exists("test")

    def test_list_sorted_by_modified(self, repo):
        """Should list datasets sorted by modified time."""
        repo.save(
            "old",
            DatasetData(
                name="old",
                profile="miappe",
                version="1.2",
                modified="2024-01-01T00:00:00",
            ),
        )
        repo.save(
            "new",
            DatasetData(
                name="new",
                profile="miappe",
                version="1.2",
                modified="2024-12-31T00:00:00",
            ),
        )

        result = repo.list()
        assert len(result) == 2
        assert result[0].name == "new"
        assert result[1].name == "old"
