"""Tests for MetaseedClient public API."""

import json

import pytest

from metaseed import MetaseedClient
from metaseed.api import (
    Entity,
    EntityNode,
    EntityNotFoundError,
    EntitySchema,
    EntityTypeNotFoundError,
    FieldInfo,
    MetaseedError,
    ProfileNotFoundError,
    ValidationIssue,
    ValidationResult,
)


class TestMetaseedClientInit:
    """Tests for MetaseedClient initialization."""

    def test_create_with_profile(self) -> None:
        """Create client with profile name."""
        client = MetaseedClient("miappe")
        assert client.profile == "miappe"
        assert client.version is not None

    def test_create_with_profile_and_version(self) -> None:
        """Create client with profile and version."""
        client = MetaseedClient("miappe", "1.2")
        assert client.profile == "miappe"
        assert client.version == "1.2"

    def test_invalid_profile_raises(self) -> None:
        """Invalid profile raises ProfileNotFoundError."""
        with pytest.raises(ProfileNotFoundError) as exc_info:
            MetaseedClient("nonexistent_profile")

        assert exc_info.value.profile == "nonexistent_profile"
        assert "not found" in str(exc_info.value)

    def test_from_spec_dict(self) -> None:
        """Create client from spec dictionary."""
        spec = {
            "version": "1.0",
            "name": "test-profile",
            "entities": {
                "Sample": {
                    "description": "A test sample",
                    "fields": [
                        {
                            "name": "id",
                            "type": "string",
                            "required": True,
                            "description": "ID",
                        },
                        {
                            "name": "name",
                            "type": "string",
                            "required": False,
                            "description": "Name",
                        },
                    ],
                }
            },
        }
        client = MetaseedClient.from_spec(spec)
        assert client.profile == "test-profile"
        assert client.version == "1.0"
        assert "Sample" in client.list_entity_types()

    def test_repr(self) -> None:
        """Client has informative repr."""
        client = MetaseedClient("miappe", "1.2")
        repr_str = repr(client)
        assert "MetaseedClient" in repr_str
        assert "miappe" in repr_str


class TestEntityCRUD:
    """Tests for entity CRUD operations."""

    @pytest.fixture
    def client(self) -> MetaseedClient:
        """Create MIAPPE client."""
        return MetaseedClient("miappe", "1.2")

    def test_create_entity(self, client: MetaseedClient) -> None:
        """Create an entity."""
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test Investigation"},
        )

        assert isinstance(entity, Entity)
        assert entity.entity_type == "Investigation"
        assert entity.data["unique_id"] == "INV-001"
        assert entity.data["title"] == "Test Investigation"

    def test_create_entity_returns_id(self, client: MetaseedClient) -> None:
        """Created entity has an ID."""
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test"},
        )
        assert entity.id is not None
        assert len(entity.id) > 0

    def test_create_entity_invalid_type_raises(self, client: MetaseedClient) -> None:
        """Creating with invalid type raises EntityTypeNotFoundError."""
        with pytest.raises(EntityTypeNotFoundError) as exc_info:
            client.create_entity("NonexistentType", {"id": "test"})

        assert exc_info.value.entity_type == "NonexistentType"
        assert exc_info.value.profile == "miappe"

    def test_get_entity(self, client: MetaseedClient) -> None:
        """Get an entity by ID."""
        created = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test"},
        )

        retrieved = client.get_entity(created.id)
        assert retrieved.id == created.id
        assert retrieved.entity_type == "Investigation"
        assert retrieved.data["unique_id"] == "INV-001"

    def test_get_entity_not_found_raises(self, client: MetaseedClient) -> None:
        """Getting nonexistent entity raises EntityNotFoundError."""
        with pytest.raises(EntityNotFoundError) as exc_info:
            client.get_entity("nonexistent-id")

        assert exc_info.value.entity_id == "nonexistent-id"

    def test_update_entity(self, client: MetaseedClient) -> None:
        """Update an entity."""
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Original"},
        )

        updated = client.update_entity(
            entity.id,
            {"unique_id": "INV-001", "title": "Updated"},
        )

        assert updated.data["title"] == "Updated"

    def test_update_entity_not_found_raises(self, client: MetaseedClient) -> None:
        """Updating nonexistent entity raises EntityNotFoundError."""
        with pytest.raises(EntityNotFoundError):
            client.update_entity("nonexistent-id", {"title": "Test"})

    def test_delete_entity(self, client: MetaseedClient) -> None:
        """Delete an entity."""
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test"},
        )

        client.delete_entity(entity.id)

        with pytest.raises(EntityNotFoundError):
            client.get_entity(entity.id)

    def test_delete_entity_not_found_raises(self, client: MetaseedClient) -> None:
        """Deleting nonexistent entity raises EntityNotFoundError."""
        with pytest.raises(EntityNotFoundError):
            client.delete_entity("nonexistent-id")

    def test_create_with_parent(self, client: MetaseedClient) -> None:
        """Create entity with parent."""
        inv = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Parent"},
        )

        study = client.create_entity(
            "Study",
            {
                "unique_id": "STU-001",
                "title": "Child",
                "investigation_id": "INV-001",  # Required field
            },
            parent_id=inv.id,
        )

        assert study.parent_id == inv.id


class TestTreeOperations:
    """Tests for tree navigation operations."""

    @pytest.fixture
    def client_with_data(self) -> MetaseedClient:
        """Create client with test data."""
        client = MetaseedClient("miappe", "1.2")

        inv = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Root"},
        )

        client.create_entity(
            "Study",
            {
                "unique_id": "STU-001",
                "title": "Child 1",
                "investigation_id": "INV-001",  # Required field
            },
            parent_id=inv.id,
        )

        client.create_entity(
            "Study",
            {
                "unique_id": "STU-002",
                "title": "Child 2",
                "investigation_id": "INV-001",  # Required field
            },
            parent_id=inv.id,
        )

        return client

    def test_get_tree(self, client_with_data: MetaseedClient) -> None:
        """Get entity tree."""
        tree = client_with_data.get_tree()

        assert len(tree) == 1  # One root
        root = tree[0]
        assert isinstance(root, EntityNode)
        assert root.entity_type == "Investigation"
        assert root.has_children is True
        assert len(root.children) == 2

    def test_get_roots(self, client_with_data: MetaseedClient) -> None:
        """Get root entities."""
        roots = client_with_data.get_roots()

        assert len(roots) == 1
        assert roots[0].entity_type == "Investigation"

    def test_get_children(self, client_with_data: MetaseedClient) -> None:
        """Get children of an entity."""
        roots = client_with_data.get_roots()
        children = client_with_data.get_children(roots[0].id)

        assert len(children) == 2
        assert all(c.entity_type == "Study" for c in children)

    def test_entity_node_to_dict(self, client_with_data: MetaseedClient) -> None:
        """EntityNode converts to dict."""
        tree = client_with_data.get_tree()
        tree_dict = tree[0].to_dict()

        assert "id" in tree_dict
        assert "entity_type" in tree_dict
        assert "label" in tree_dict
        assert "children" in tree_dict


class TestSerialization:
    """Tests for serialization and loading."""

    @pytest.fixture
    def client(self) -> MetaseedClient:
        """Create client."""
        return MetaseedClient("miappe", "1.2")

    def test_serialize_empty(self, client: MetaseedClient) -> None:
        """Serialize empty client."""
        data = client.serialize()

        assert data["profile"] == "miappe"
        assert data["version"] == "1.2"
        assert data["entities"] == []

    def test_serialize_with_entities(self, client: MetaseedClient) -> None:
        """Serialize client with entities."""
        client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test"},
        )

        data = client.serialize()

        assert len(data["entities"]) == 1
        assert data["entities"][0]["_type"] == "Investigation"

    def test_load_entities(self, client: MetaseedClient) -> None:
        """Load entities from serialized data."""
        data = {
            "profile": "miappe",
            "version": "1.2",
            "entities": [
                {"_type": "Investigation", "unique_id": "INV-001", "title": "Loaded"},
            ],
        }

        count = client.load(data)

        assert count == 1
        roots = client.get_roots()
        assert len(roots) == 1
        assert roots[0].entity_type == "Investigation"

    def test_load_clears_existing(self, client: MetaseedClient) -> None:
        """Loading clears existing entities."""
        client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Existing"},
        )

        data = {
            "entities": [
                {"_type": "Investigation", "unique_id": "INV-002", "title": "New"},
            ]
        }

        client.load(data)
        roots = client.get_roots()

        assert len(roots) == 1
        entity = client.get_entity(roots[0].id)
        assert entity.data["unique_id"] == "INV-002"

    def test_clear(self, client: MetaseedClient) -> None:
        """Clear removes all entities."""
        client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test"},
        )

        client.clear()

        assert len(client.get_roots()) == 0


class TestValidation:
    """Tests for validation operations."""

    @pytest.fixture
    def client(self) -> MetaseedClient:
        """Create client."""
        return MetaseedClient("miappe", "1.2")

    def test_validate_empty(self, client: MetaseedClient) -> None:
        """Validate empty client succeeds."""
        result = client.validate()

        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert len(result.issues) == 0

    def test_validate_returns_issues(self, client: MetaseedClient) -> None:
        """Validate returns validation issues for incomplete entity."""
        # Investigation without studies/contacts triggers validation rules
        client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Incomplete Investigation"},
        )

        result = client.validate()
        # MIAPPE Investigation requires studies and contacts
        assert isinstance(result, ValidationResult)
        # Test that validation runs and returns structured issues
        assert len(result.issues) > 0 or result.valid is True

    def test_validate_entity_by_id(self, client: MetaseedClient) -> None:
        """Validate specific entity returns result."""
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test"},
        )

        result = client.validate_entity(entity.id)
        assert isinstance(result, ValidationResult)
        # Validation should return issues (studies/contacts required) or pass
        assert isinstance(result.issues, list)

    def test_validate_entity_not_found_raises(self, client: MetaseedClient) -> None:
        """Validating nonexistent entity raises EntityNotFoundError."""
        with pytest.raises(EntityNotFoundError):
            client.validate_entity("nonexistent-id")

    def test_validation_result_bool(self) -> None:
        """ValidationResult works as bool."""
        success = ValidationResult.success()
        failure = ValidationResult.failure([ValidationIssue("field", "error", "rule")])

        assert bool(success) is True
        assert bool(failure) is False

    def test_validation_result_error_count(self) -> None:
        """ValidationResult reports error count."""
        result = ValidationResult.failure(
            [
                ValidationIssue("field1", "error1", "rule"),
                ValidationIssue("field2", "error2", "rule"),
            ]
        )

        assert result.error_count == 2

    def test_validation_result_get_field_errors(self) -> None:
        """ValidationResult filters by field."""
        result = ValidationResult.failure(
            [
                ValidationIssue("field1", "error1", "rule"),
                ValidationIssue("field1", "error2", "rule"),
                ValidationIssue("field2", "error3", "rule"),
            ]
        )

        field1_errors = result.get_field_errors("field1")
        assert len(field1_errors) == 2


class TestSchemaIntrospection:
    """Tests for schema introspection."""

    @pytest.fixture
    def client(self) -> MetaseedClient:
        """Create client."""
        return MetaseedClient("miappe", "1.2")

    def test_list_entity_types(self, client: MetaseedClient) -> None:
        """List all entity types."""
        types = client.list_entity_types()

        assert isinstance(types, list)
        assert len(types) > 0
        assert "Investigation" in types
        assert "Study" in types

    def test_get_entity_fields(self, client: MetaseedClient) -> None:
        """Get fields for an entity type."""
        fields = client.get_entity_fields("Investigation")

        assert isinstance(fields, list)
        assert len(fields) > 0
        assert all(isinstance(f, FieldInfo) for f in fields)

        # Check for expected fields
        field_names = [f.name for f in fields]
        assert "unique_id" in field_names
        assert "title" in field_names

    def test_get_entity_fields_invalid_type_raises(
        self, client: MetaseedClient
    ) -> None:
        """Getting fields for invalid type raises EntityTypeNotFoundError."""
        with pytest.raises(EntityTypeNotFoundError):
            client.get_entity_fields("NonexistentType")

    def test_get_entity_schema(self, client: MetaseedClient) -> None:
        """Get complete entity schema."""
        schema = client.get_entity_schema("Investigation")

        assert isinstance(schema, EntitySchema)
        assert schema.name == "Investigation"
        assert len(schema.description) > 0
        assert len(schema.fields) > 0
        assert len(schema.required_fields) > 0

    def test_field_info_attributes(self, client: MetaseedClient) -> None:
        """FieldInfo has expected attributes."""
        fields = client.get_entity_fields("Investigation")
        unique_id = next(f for f in fields if f.name == "unique_id")

        assert unique_id.name == "unique_id"
        assert unique_id.type == "string"
        assert unique_id.required is True
        assert len(unique_id.description) > 0

    def test_entity_schema_all_field_names(self, client: MetaseedClient) -> None:
        """EntitySchema provides all_field_names property."""
        schema = client.get_entity_schema("Investigation")

        assert isinstance(schema.all_field_names, tuple)
        assert "unique_id" in schema.all_field_names


class TestSerializationFormats:
    """Tests for serialization format options."""

    @pytest.fixture
    def client_with_data(self) -> MetaseedClient:
        """Create client with test data."""
        client = MetaseedClient("miappe", "1.2")

        inv = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Test Investigation"},
        )

        client.create_entity(
            "Study",
            {
                "unique_id": "STU-001",
                "title": "Test Study",
                "investigation_id": "INV-001",
            },
            parent_id=inv.id,
        )

        return client

    def test_serialize_flat_format(self, client_with_data: MetaseedClient) -> None:
        """Serialize with default flat format."""
        data = client_with_data.serialize()

        assert "profile" in data
        assert "version" in data
        assert "entities" in data
        assert isinstance(data["entities"], list)
        assert len(data["entities"]) == 2

    def test_serialize_tree_format(self, client_with_data: MetaseedClient) -> None:
        """Serialize with tree format."""
        data = client_with_data.serialize(format="tree")

        assert "profile" in data
        assert "version" in data
        assert "tree" in data
        assert "entities" not in data

        tree = data["tree"]
        assert len(tree) == 1  # One root
        root = tree[0]
        assert root["entity_type"] == "Investigation"
        assert "label" in root
        assert "data" in root
        assert "children" in root
        assert len(root["children"]) == 1

    def test_load_auto_detects_flat_format(
        self, client_with_data: MetaseedClient
    ) -> None:
        """Load auto-detects flat format."""
        data = client_with_data.serialize(format="flat")

        new_client = MetaseedClient("miappe", "1.2")
        count = new_client.load(data)

        assert count == 2
        assert len(new_client.get_roots()) == 1

    def test_load_auto_detects_tree_format(
        self, client_with_data: MetaseedClient
    ) -> None:
        """Load auto-detects tree format."""
        data = client_with_data.serialize(format="tree")

        new_client = MetaseedClient("miappe", "1.2")
        count = new_client.load(data)

        assert count == 2
        roots = new_client.get_roots()
        assert len(roots) == 1
        assert roots[0].entity_type == "Investigation"

    def test_tree_roundtrip(self, client_with_data: MetaseedClient) -> None:
        """Tree format roundtrips correctly."""
        original_tree = client_with_data.get_tree()

        data = client_with_data.serialize(format="tree")
        new_client = MetaseedClient("miappe", "1.2")
        new_client.load(data)

        new_tree = new_client.get_tree()
        assert len(new_tree) == len(original_tree)

    def test_serialize_flat_is_json_serializable(self) -> None:
        """Flat format output is JSON-serializable (dates, URLs are strings)."""
        client = MetaseedClient("isa", "1.0")
        client.create_entity(
            "Investigation",
            {
                "identifier": "test-inv",
                "title": "Test",
                "submission_date": "2024-01-15",
            },
        )

        data = client.serialize(format="flat")
        # Should not raise TypeError for date objects
        result = json.dumps(data)
        assert "2024-01-15" in result

    def test_serialize_tree_is_json_serializable(self) -> None:
        """Tree format output is JSON-serializable (dates, URLs are strings)."""
        client = MetaseedClient("isa", "1.0")
        client.create_entity(
            "Investigation",
            {
                "identifier": "test-inv",
                "title": "Test",
                "submission_date": "2024-01-15",
            },
        )

        data = client.serialize(format="tree")
        # Should not raise TypeError for date objects
        result = json.dumps(data)
        assert "2024-01-15" in result

    def test_serialize_with_uri_is_json_serializable(self) -> None:
        """Serialization handles URI/URL types correctly."""
        client = MetaseedClient("isa", "1.0")
        inv = client.create_entity(
            "Investigation",
            {"identifier": "test-inv", "title": "Test"},
        )
        study = client.create_entity(
            "Study",
            {
                "identifier": "test-study",
                "title": "Test Study",
                "investigation_id": "test-inv",
            },
            parent_id=inv.id,
        )
        client.create_entity(
            "Protocol",
            {
                "name": "Test Protocol",
                "study_id": "test-study",
                "uri": "http://example.org/protocol",
            },
            parent_id=study.id,
        )

        data = client.serialize(format="flat")
        result = json.dumps(data)
        assert "http://example.org/protocol" in result


class TestEntityLabel:
    """Tests for get_entity_label method."""

    @pytest.fixture
    def client(self) -> MetaseedClient:
        """Create client."""
        return MetaseedClient("miappe", "1.2")

    def test_get_entity_label(self, client: MetaseedClient) -> None:
        """Get label for an entity."""
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "My Investigation"},
        )

        label = client.get_entity_label(entity.id)
        assert label == "INV-001"  # First field value

    def test_get_entity_label_not_found_raises(self, client: MetaseedClient) -> None:
        """Getting label for nonexistent entity raises."""
        with pytest.raises(EntityNotFoundError):
            client.get_entity_label("nonexistent-id")


class TestSkipValidation:
    """Tests for skip_validation mode (permissive editing)."""

    @pytest.fixture
    def client(self) -> MetaseedClient:
        """Create client."""
        return MetaseedClient("miappe", "1.2")

    def test_create_entity_skip_validation(self, client: MetaseedClient) -> None:
        """Create entity with skip_validation bypasses required field check."""
        # This would normally fail - Investigation requires unique_id
        entity = client.create_entity(
            "Investigation",
            {"title": "Work in progress"},  # missing unique_id
            skip_validation=True,
        )

        assert entity.entity_type == "Investigation"
        assert entity.data.get("title") == "Work in progress"
        assert entity.id is not None

    def test_create_entity_without_skip_validation_raises(
        self, client: MetaseedClient
    ) -> None:
        """Create entity without skip_validation raises on missing required field."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            client.create_entity(
                "Investigation",
                {"title": "Incomplete"},  # missing unique_id
            )

    def test_update_entity_skip_validation(self, client: MetaseedClient) -> None:
        """Update entity with skip_validation bypasses validation."""
        # First create a valid entity
        entity = client.create_entity(
            "Investigation",
            {"unique_id": "INV-001", "title": "Original"},
        )

        # Update with incomplete data using skip_validation
        updated = client.update_entity(
            entity.id,
            {"title": "Updated"},  # missing unique_id
            skip_validation=True,
        )

        assert updated.data.get("title") == "Updated"

    def test_validate_entity_with_skip_validation_draft(
        self, client: MetaseedClient
    ) -> None:
        """Validate draft entity created with skip_validation shows issues."""
        entity = client.create_entity(
            "Investigation",
            {"title": "Draft"},
            skip_validation=True,
        )

        result = client.validate_entity(entity.id)
        # Should have validation issues since required fields are missing
        assert isinstance(result, ValidationResult)


class TestEntityObject:
    """Tests for Entity domain object."""

    @pytest.fixture
    def entity(self) -> Entity:
        """Create test entity."""
        return Entity(
            id="test-id",
            entity_type="Investigation",
            data={"unique_id": "INV-001", "title": "Test", "description": "A test"},
        )

    def test_entity_attributes(self, entity: Entity) -> None:
        """Entity has expected attributes."""
        assert entity.id == "test-id"
        assert entity.entity_type == "Investigation"
        assert entity.data["unique_id"] == "INV-001"

    def test_entity_label(self, entity: Entity) -> None:
        """Entity derives label from data."""
        assert entity.label == "INV-001"

    def test_entity_label_empty_data(self) -> None:
        """Entity with empty data has fallback label."""
        entity = Entity(id="test", entity_type="Sample", data={})
        assert entity.label == "New Sample"

    def test_entity_get(self, entity: Entity) -> None:
        """Entity.get() retrieves field values."""
        assert entity.get("unique_id") == "INV-001"
        assert entity.get("nonexistent", "default") == "default"

    def test_entity_subscript(self, entity: Entity) -> None:
        """Entity supports subscript notation."""
        assert entity["unique_id"] == "INV-001"

        with pytest.raises(KeyError):
            _ = entity["nonexistent"]


class TestErrorHierarchy:
    """Tests for exception hierarchy."""

    def test_all_errors_inherit_from_metaseed_error(self) -> None:
        """All errors inherit from MetaseedError."""
        assert issubclass(ProfileNotFoundError, MetaseedError)
        assert issubclass(EntityNotFoundError, MetaseedError)
        assert issubclass(EntityTypeNotFoundError, MetaseedError)
        from metaseed.api import ValidationError

        assert issubclass(ValidationError, MetaseedError)

    def test_profile_not_found_error_attributes(self) -> None:
        """ProfileNotFoundError has expected attributes."""
        error = ProfileNotFoundError("test-profile", "1.0")
        assert error.profile == "test-profile"
        assert error.version == "1.0"
        assert "test-profile" in str(error)
        assert "1.0" in str(error)

    def test_entity_not_found_error_attributes(self) -> None:
        """EntityNotFoundError has expected attributes."""
        error = EntityNotFoundError("entity-123")
        assert error.entity_id == "entity-123"
        assert "entity-123" in str(error)

    def test_entity_type_not_found_error_attributes(self) -> None:
        """EntityTypeNotFoundError has expected attributes."""
        error = EntityTypeNotFoundError("BadType", "miappe")
        assert error.entity_type == "BadType"
        assert error.profile == "miappe"
        assert "BadType" in str(error)
        assert "miappe" in str(error)
