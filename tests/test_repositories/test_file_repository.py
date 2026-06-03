"""Tests for FileEntityRepository."""

import json

import pytest

from metaseed.repositories.file import FileEntityRepository


class TestFileEntityRepositoryInit:
    """Test repository initialization."""

    def test_create_with_defaults(self):
        """Can create repository with default settings."""
        repo = FileEntityRepository()
        assert repo._profile == "miappe"
        assert repo._path is None
        assert len(repo._entities) == 0

    def test_create_with_path(self, tmp_path):
        """Can create repository with custom path."""
        path = tmp_path / "test.json"
        repo = FileEntityRepository(dataset_path=path, profile="isa", version="1.0")
        assert repo._path == path
        assert repo._profile == "isa"
        assert repo._version == "1.0"

    def test_loads_existing_file(self, tmp_path):
        """Loads data from existing file on init."""
        path = tmp_path / "existing.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "abc123", "entity_type": "Investigation", "label": "Test"}
            ],
        }
        path.write_text(json.dumps(data))

        repo = FileEntityRepository(dataset_path=path)
        assert len(repo._entities) == 1
        assert "abc123" in repo._entities


class TestFromDatasetName:
    """Test from_dataset_name factory method."""

    def test_creates_path_in_default_dir(self, tmp_path):
        """Creates path using dataset name."""
        repo = FileEntityRepository.from_dataset_name("mydata", datasets_dir=tmp_path)
        assert repo._path == tmp_path / "mydata.json"

    def test_creates_directory_if_needed(self, tmp_path):
        """Creates datasets directory if it doesn't exist."""
        custom_dir = tmp_path / "custom" / "datasets"
        FileEntityRepository.from_dataset_name("test", datasets_dir=custom_dir)
        assert custom_dir.exists()


class TestListEntities:
    """Test list_entities method."""

    @pytest.fixture
    def repo_with_data(self, tmp_path):
        """Repository with test data."""
        path = tmp_path / "test.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "inv1", "entity_type": "Investigation", "label": "Inv 1"},
                {"id": "stu1", "entity_type": "Study", "label": "Study 1"},
                {"id": "stu2", "entity_type": "Study", "label": "Study 2"},
            ],
        }
        path.write_text(json.dumps(data))
        return FileEntityRepository(dataset_path=path)

    def test_list_all(self, repo_with_data):
        """Lists all entities without filter."""
        entities = repo_with_data.list_entities()
        assert len(entities) == 3

    def test_filter_by_type(self, repo_with_data):
        """Filters entities by type."""
        studies = repo_with_data.list_entities(entity_type="Study")
        assert len(studies) == 2
        assert all(e.entity_type == "Study" for e in studies)


class TestGetEntity:
    """Test get_entity method."""

    def test_get_existing(self, tmp_path):
        """Gets existing entity by ID."""
        path = tmp_path / "test.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "abc123", "entity_type": "Investigation", "label": "Test"}
            ],
        }
        path.write_text(json.dumps(data))
        repo = FileEntityRepository(dataset_path=path)

        entity = repo.get_entity("abc123")
        assert entity is not None
        assert entity.id == "abc123"
        assert entity.entity_type == "Investigation"

    def test_get_nonexistent(self, tmp_path):
        """Returns None for nonexistent ID."""
        path = tmp_path / "test.json"
        repo = FileEntityRepository(dataset_path=path)
        assert repo.get_entity("nonexistent") is None


class TestCreateEntity:
    """Test create_entity method."""

    @pytest.fixture
    def empty_repo(self, tmp_path):
        """Empty repository for testing."""
        path = tmp_path / "test.json"
        return FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")

    def test_create_root_entity(self, empty_repo):
        """Creates a root entity."""
        entity = empty_repo.create_entity(
            entity_type="Investigation",
            data={"unique_id": "INV-001", "title": "Test Investigation"},
        )

        assert entity.id is not None
        assert entity.entity_type == "Investigation"
        assert entity.data["unique_id"] == "INV-001"
        assert entity.parent_id is None

    def test_create_saves_to_file(self, empty_repo):
        """Creating entity persists to file."""
        empty_repo.create_entity(
            entity_type="Investigation",
            data={"unique_id": "INV-001", "title": "Test"},
        )

        assert empty_repo._path.exists()
        saved_data = json.loads(empty_repo._path.read_text())
        assert len(saved_data["entities"]) == 1

    def test_create_child_entity(self, empty_repo):
        """Creates entity as child of parent."""
        parent = empty_repo.create_entity(
            entity_type="Investigation",
            data={"unique_id": "INV-001", "title": "Parent"},
        )

        child = empty_repo.create_entity(
            entity_type="Study",
            data={
                "unique_id": "STU-001",
                "title": "Child Study",
                "investigation_id": "INV-001",  # Required reference field
            },
            parent_id=parent.id,
        )

        assert child.parent_id == parent.id
        assert child in parent.children

    def test_create_invalid_type_raises(self, empty_repo):
        """Raises error for invalid entity type."""
        with pytest.raises(ValueError, match="Unknown entity type"):
            empty_repo.create_entity(
                entity_type="NonexistentType",
                data={"unique_id": "X"},
            )

    def test_create_invalid_parent_raises(self, empty_repo):
        """Raises error for invalid parent ID."""
        with pytest.raises(ValueError, match="Parent entity not found"):
            empty_repo.create_entity(
                entity_type="Study",
                data={"unique_id": "STU-001", "title": "Study"},
                parent_id="nonexistent",
            )


class TestUpdateEntity:
    """Test update_entity method."""

    @pytest.fixture
    def repo_with_entity(self, tmp_path):
        """Repository with one entity."""
        path = tmp_path / "test.json"
        repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")
        repo.create_entity(
            entity_type="Investigation",
            data={"unique_id": "INV-001", "title": "Original"},
        )
        return repo

    def test_update_data(self, repo_with_entity):
        """Updates entity data."""
        entity_id = next(iter(repo_with_entity._entities.keys()))
        updated = repo_with_entity.update_entity(entity_id, {"title": "Updated Title"})

        assert updated.data["title"] == "Updated Title"
        assert updated.data["unique_id"] == "INV-001"  # Preserved

    def test_update_saves_to_file(self, repo_with_entity):
        """Update persists to file."""
        entity_id = next(iter(repo_with_entity._entities.keys()))
        repo_with_entity.update_entity(entity_id, {"title": "Updated"})

        saved_data = json.loads(repo_with_entity._path.read_text())
        entity_data = saved_data["entities"][0]
        assert entity_data["title"] == "Updated"

    def test_update_nonexistent_raises(self, repo_with_entity):
        """Raises error for nonexistent entity."""
        with pytest.raises(ValueError, match="Entity not found"):
            repo_with_entity.update_entity("nonexistent", {"title": "X"})


class TestDeleteEntity:
    """Test delete_entity method."""

    @pytest.fixture
    def repo_with_hierarchy(self, tmp_path):
        """Repository with parent-child hierarchy."""
        path = tmp_path / "test.json"
        repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")

        parent = repo.create_entity(
            entity_type="Investigation",
            data={"unique_id": "INV-001", "title": "Parent"},
        )
        repo.create_entity(
            entity_type="Study",
            data={
                "unique_id": "STU-001",
                "title": "Child",
                "investigation_id": "INV-001",  # Required reference field
            },
            parent_id=parent.id,
        )
        return repo

    def test_delete_removes_entity(self, repo_with_hierarchy):
        """Deletes entity from repository."""
        entities = list(repo_with_hierarchy._entities.values())
        study = next(e for e in entities if e.entity_type == "Study")

        result = repo_with_hierarchy.delete_entity(study.id)
        assert result is True
        assert study.id not in repo_with_hierarchy._entities

    def test_delete_cascades_children(self, repo_with_hierarchy):
        """Deleting parent also deletes children."""
        entities = list(repo_with_hierarchy._entities.values())
        inv = next(e for e in entities if e.entity_type == "Investigation")

        repo_with_hierarchy.delete_entity(inv.id)
        assert len(repo_with_hierarchy._entities) == 0  # Both deleted

    def test_delete_nonexistent_returns_false(self, repo_with_hierarchy):
        """Returns False for nonexistent entity."""
        result = repo_with_hierarchy.delete_entity("nonexistent")
        assert result is False


class TestGetTree:
    """Test get_tree method."""

    def test_returns_roots(self, tmp_path):
        """Returns list of root entities."""
        path = tmp_path / "test.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "root1", "entity_type": "Investigation", "label": "Root 1"},
                {"id": "root2", "entity_type": "Investigation", "label": "Root 2"},
            ],
        }
        path.write_text(json.dumps(data))
        repo = FileEntityRepository(dataset_path=path)

        tree = repo.get_tree()
        assert len(tree) == 2

    def test_tree_includes_children(self, tmp_path):
        """Tree includes nested children."""
        path = tmp_path / "test.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "parent", "entity_type": "Investigation", "label": "Parent"},
                {
                    "id": "child",
                    "entity_type": "Study",
                    "label": "Child",
                    "parent_id": "parent",
                },
            ],
        }
        path.write_text(json.dumps(data))
        repo = FileEntityRepository(dataset_path=path)

        tree = repo.get_tree()
        assert len(tree) == 1  # One root
        assert len(tree[0].children) == 1  # With one child


class TestProfileMethods:
    """Test profile and version methods."""

    def test_get_profile(self, tmp_path):
        """Returns current profile."""
        repo = FileEntityRepository(
            dataset_path=tmp_path / "test.json", profile="isa", version="1.0"
        )
        assert repo.get_profile() == "isa"

    def test_get_version(self, tmp_path):
        """Returns current version."""
        repo = FileEntityRepository(
            dataset_path=tmp_path / "test.json", profile="miappe", version="1.2"
        )
        assert repo.get_version() == "1.2"

    def test_set_profile(self, tmp_path):
        """Sets profile and version."""
        repo = FileEntityRepository(
            dataset_path=tmp_path / "test.json", profile="miappe", version="1.1"
        )
        repo.set_profile("isa", "1.0")
        assert repo.get_profile() == "isa"
        assert repo.get_version() == "1.0"
        assert repo._facade is None  # Reset


class TestReload:
    """Test reload method."""

    def test_reload_from_file(self, tmp_path):
        """Reloads data from file."""
        path = tmp_path / "test.json"
        initial_data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "abc", "entity_type": "Investigation", "label": "Init"}
            ],
        }
        path.write_text(json.dumps(initial_data))
        repo = FileEntityRepository(dataset_path=path)

        # Modify file externally
        updated_data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "abc", "entity_type": "Investigation", "label": "Init"},
                {"id": "def", "entity_type": "Study", "label": "New"},
            ],
        }
        path.write_text(json.dumps(updated_data))

        repo.reload()
        assert len(repo._entities) == 2


class TestParseEntities:
    """Test _parse_entities internal method."""

    def test_handles_old_format(self, tmp_path):
        """Parses old format with _node_id and _type."""
        path = tmp_path / "test.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"_node_id": "abc123", "_type": "Investigation", "title": "Test"},
            ],
        }
        path.write_text(json.dumps(data))
        repo = FileEntityRepository(dataset_path=path)

        assert "abc123" in repo._entities
        entity = repo._entities["abc123"]
        assert entity.entity_type == "Investigation"

    def test_derives_label_if_missing(self, tmp_path):
        """Derives label from data if not present."""
        path = tmp_path / "test.json"
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"id": "abc", "entity_type": "Investigation", "unique_id": "INV-001"},
            ],
        }
        path.write_text(json.dumps(data))
        repo = FileEntityRepository(dataset_path=path)

        entity = repo._entities["abc"]
        assert entity.label  # Should have derived label
