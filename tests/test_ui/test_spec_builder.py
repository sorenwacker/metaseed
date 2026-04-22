"""Tests for the Spec Builder UI.

Tests helpers and routes for creating/editing ProfileSpec specifications.
"""

import pytest
from fastapi.testclient import TestClient

from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    ValidationRuleSpec,
)
from metaseed.ui.routes import AppState, create_app
from metaseed.ui.spec_builder_helpers import (
    clone_spec,
    create_empty_spec,
    list_available_templates,
    spec_to_yaml,
    validate_entity_name,
    validate_field_name,
)
from metaseed.ui.spec_builder_state import SpecBuilderState


@pytest.fixture
def client():
    """Create a test client with fresh state."""
    state = AppState()
    app = create_app(state)
    return TestClient(app)


@pytest.fixture
def sample_spec():
    """Create a sample ProfileSpec for testing."""
    return ProfileSpec(
        version="1.0",
        name="test-profile",
        display_name="Test Profile",
        description="A test profile for unit testing.",
        ontology="TEST",
        root_entity="TestEntity",
        validation_rules=[
            ValidationRuleSpec(
                name="test_rule",
                description="A test validation rule",
                applies_to=["TestEntity"],
                field="name",
                pattern="^[A-Za-z]+$",
            )
        ],
        entities={
            "TestEntity": EntityDefSpec(
                ontology_term="TEST:001",
                description="A test entity",
                fields=[
                    FieldSpec(
                        name="unique_id",
                        type=FieldType.STRING,
                        required=True,
                        description="Unique identifier",
                    ),
                    FieldSpec(
                        name="name",
                        type=FieldType.STRING,
                        required=True,
                        description="Name of the entity",
                    ),
                    FieldSpec(
                        name="count",
                        type=FieldType.INTEGER,
                        required=False,
                        description="A count value",
                        constraints=Constraints(minimum=0, maximum=100),
                    ),
                ],
            )
        },
    )


class TestSpecBuilderState:
    """Tests for SpecBuilderState dataclass."""

    def test_initial_state(self):
        """New state has expected defaults."""
        state = SpecBuilderState()
        assert state.spec is None
        assert state.editing_entity is None
        assert state.editing_field_idx is None
        assert state.editing_rule_idx is None
        assert state.template_source is None
        assert state.has_unsaved_changes is False

    def test_reset(self, sample_spec):
        """Reset clears all state."""
        state = SpecBuilderState()
        state.spec = sample_spec
        state.editing_entity = "TestEntity"
        state.has_unsaved_changes = True
        state.template_source = ("miappe", "1.2")

        state.reset()

        assert state.spec is None
        assert state.editing_entity is None
        assert state.has_unsaved_changes is False
        assert state.template_source is None

    def test_mark_changed(self):
        """mark_changed sets has_unsaved_changes."""
        state = SpecBuilderState()
        assert state.has_unsaved_changes is False
        state.mark_changed()
        assert state.has_unsaved_changes is True

    def test_mark_saved(self):
        """mark_saved clears has_unsaved_changes."""
        state = SpecBuilderState()
        state.has_unsaved_changes = True
        state.mark_saved()
        assert state.has_unsaved_changes is False

    def test_is_active(self, sample_spec):
        """is_active returns True when spec is set."""
        state = SpecBuilderState()
        assert state.is_active() is False
        state.spec = sample_spec
        assert state.is_active() is True

    def test_get_entity_names(self, sample_spec):
        """get_entity_names returns entity names from spec."""
        state = SpecBuilderState()
        assert state.get_entity_names() == []
        state.spec = sample_spec
        assert "TestEntity" in state.get_entity_names()


class TestSpecBuilderHelpers:
    """Tests for spec builder helper functions."""

    def test_create_empty_spec(self):
        """create_empty_spec returns valid empty ProfileSpec."""
        spec = create_empty_spec()
        assert isinstance(spec, ProfileSpec)
        assert spec.version == "1.0"
        assert spec.name == ""
        assert spec.entities == {}
        assert spec.validation_rules == []

    def test_clone_spec_miappe(self):
        """clone_spec creates independent copy of MIAPPE spec."""
        spec = clone_spec("miappe", "1.1")
        assert isinstance(spec, ProfileSpec)
        assert spec.name == "miappe"
        assert spec.version == "1.1"
        assert "Investigation" in spec.entities
        # Verify it's a copy
        spec.name = "modified"
        original = clone_spec("miappe", "1.1")
        assert original.name == "miappe"

    def test_clone_spec_invalid_profile(self):
        """clone_spec raises ValueError for invalid profile."""
        with pytest.raises(ValueError):
            clone_spec("nonexistent", "1.0")

    def test_spec_to_yaml(self, sample_spec):
        """spec_to_yaml converts spec to valid YAML string."""
        yaml_str = spec_to_yaml(sample_spec)
        assert isinstance(yaml_str, str)
        assert "name: test-profile" in yaml_str
        assert "version: '1.0'" in yaml_str or 'version: "1.0"' in yaml_str
        assert "TestEntity:" in yaml_str
        assert "unique_id" in yaml_str

    def test_list_available_templates(self):
        """list_available_templates returns list of profiles."""
        templates = list_available_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0
        # Should include miappe
        names = [t["name"] for t in templates]
        assert "miappe" in names
        # Each template should have required fields
        for template in templates:
            assert "name" in template
            assert "display_name" in template
            assert "versions" in template
            assert len(template["versions"]) > 0

    def test_validate_entity_name_valid(self):
        """validate_entity_name returns None for valid names."""
        assert validate_entity_name("Investigation") is None
        assert validate_entity_name("BiologicalMaterial") is None
        assert validate_entity_name("Study123") is None

    def test_validate_entity_name_invalid(self):
        """validate_entity_name returns error for invalid names."""
        assert validate_entity_name("") is not None
        assert validate_entity_name("investigation") is not None  # lowercase
        assert validate_entity_name("Study-Name") is not None  # hyphen
        assert validate_entity_name("123Study") is not None  # starts with number

    def test_validate_field_name_valid(self):
        """validate_field_name returns None for valid names."""
        assert validate_field_name("unique_id") is None
        assert validate_field_name("name") is None
        assert validate_field_name("study_id123") is None
        assert validate_field_name("_private") is None

    def test_validate_field_name_invalid(self):
        """validate_field_name returns error for invalid names."""
        assert validate_field_name("") is not None
        assert validate_field_name("UniqueId") is not None  # PascalCase
        assert validate_field_name("field-name") is not None  # hyphen
        assert validate_field_name("123field") is not None  # starts with number


class TestSpecBuilderRoutes:
    """Tests for spec builder routes."""

    def test_spec_builder_index_start(self, client):
        """Spec builder index shows start options when no spec in progress."""
        response = client.get("/spec-builder")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Start from Scratch" in response.text
        assert "Clone Existing" in response.text

    def test_new_spec(self, client):
        """Creating new spec initializes empty spec."""
        response = client.get("/spec-builder/new")
        assert response.status_code == 200
        assert "Spec Builder" in response.text
        # Should show ERD editor view
        assert "Profile" in response.text
        assert "Toolbox" in response.text

    def test_clone_spec(self, client):
        """Cloning spec creates copy of existing."""
        response = client.get("/spec-builder/clone/miappe/1.1")
        assert response.status_code == 200
        assert "Spec Builder" in response.text
        assert "Cloned from miappe v1.1" in response.text

    def test_clone_spec_invalid(self, client):
        """Cloning invalid spec returns 404."""
        response = client.get("/spec-builder/clone/nonexistent/1.0")
        assert response.status_code == 404

    def test_reset_builder(self, client):
        """Reset returns to start options."""
        # First create a spec
        client.get("/spec-builder/new")
        # Then reset
        response = client.get("/spec-builder/reset")
        assert response.status_code == 200
        assert "Start from Scratch" in response.text

    def test_profile_metadata_get(self, client):
        """Get profile metadata form."""
        client.get("/spec-builder/new")
        response = client.get("/spec-builder/profile-metadata")
        assert response.status_code == 200
        assert 'name="name"' in response.text
        assert 'name="version"' in response.text

    def test_profile_metadata_update(self, client):
        """Update profile metadata."""
        client.get("/spec-builder/new")
        response = client.post(
            "/spec-builder/profile-metadata",
            data={
                "name": "my-profile",
                "version": "2.0",
                "display_name": "My Profile",
                "description": "Test description",
                "ontology": "TEST",
                "root_entity": "MyEntity",
            },
        )
        assert response.status_code == 200
        assert "my-profile" in response.text

    def test_add_entity(self, client):
        """Add new entity."""
        client.get("/spec-builder/new")
        response = client.post(
            "/spec-builder/entity",
            data={"name": "NewEntity"},
        )
        assert response.status_code == 200
        assert "NewEntity" in response.text

    def test_add_entity_invalid_name(self, client):
        """Add entity with invalid name shows error."""
        client.get("/spec-builder/new")
        response = client.post(
            "/spec-builder/entity",
            data={"name": "lowercase"},
        )
        assert response.status_code == 200
        assert "uppercase" in response.text.lower() or "PascalCase" in response.text

    def test_get_entity(self, client):
        """Get entity editor."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        response = client.get("/spec-builder/entity/TestEntity")
        assert response.status_code == 200
        assert "TestEntity" in response.text
        assert "Fields" in response.text

    def test_delete_entity(self, client):
        """Delete entity."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "ToDelete"})
        response = client.delete("/spec-builder/entity/ToDelete")
        assert response.status_code == 200
        assert "ToDelete" not in response.text

    def test_add_field(self, client):
        """Add field to entity."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        response = client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "new_field", "field_type": "string"},
        )
        assert response.status_code == 200
        assert "new_field" in response.text

    def test_update_field(self, client):
        """Update field."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "test_field", "field_type": "string"},
        )
        response = client.put(
            "/spec-builder/entity/TestEntity/field/0",
            data={
                "name": "updated_field",
                "field_type": "integer",
                "required": "true",
                "description": "Updated description",
                "ontology_term": "",
                "codename": "",
                "items": "",
                "parent_ref": "",
                "pattern": "",
                "min_length": "",
                "max_length": "",
                "minimum": "0",
                "maximum": "100",
                "enum_values": "",
            },
        )
        assert response.status_code == 200
        assert "updated_field" in response.text

    def test_delete_field(self, client):
        """Delete field from entity."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "to_delete", "field_type": "string"},
        )
        response = client.delete("/spec-builder/entity/TestEntity/field/0")
        assert response.status_code == 200
        assert "to_delete" not in response.text

    def test_add_validation_rule(self, client):
        """Add validation rule."""
        client.get("/spec-builder/new")
        response = client.post(
            "/spec-builder/validation-rule",
            data={"name": "new_rule"},
        )
        assert response.status_code == 200
        assert "new_rule" in response.text

    def test_preview_yaml(self, client):
        """Preview YAML output."""
        client.get("/spec-builder/new")
        client.post(
            "/spec-builder/profile-metadata",
            data={
                "name": "test",
                "version": "1.0",
                "display_name": "",
                "description": "",
                "ontology": "",
                "root_entity": "",
            },
        )
        response = client.get("/spec-builder/preview")
        assert response.status_code == 200
        assert "name: test" in response.text

    def test_export_yaml(self, client):
        """Export YAML file."""
        client.get("/spec-builder/new")
        client.post(
            "/spec-builder/profile-metadata",
            data={
                "name": "export-test",
                "version": "1.0",
                "display_name": "",
                "description": "",
                "ontology": "",
                "root_entity": "",
            },
        )
        response = client.get("/spec-builder/export")
        assert response.status_code == 200
        assert "application/x-yaml" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]


class TestSpecBuilderIntegration:
    """Integration tests for complete spec builder workflows."""

    def test_create_simple_spec_workflow(self, client):
        """Test creating a simple spec from scratch."""
        # Start new spec
        client.get("/spec-builder/new")

        # Set metadata
        client.post(
            "/spec-builder/profile-metadata",
            data={
                "name": "simple-spec",
                "version": "1.0",
                "display_name": "Simple Spec",
                "description": "A simple test specification",
                "ontology": "",
                "root_entity": "Document",
            },
        )

        # Add entity
        client.post("/spec-builder/entity", data={"name": "Document"})

        # Add fields
        client.post(
            "/spec-builder/entity/Document/field",
            data={"name": "identifier", "field_type": "string"},
        )
        client.put(
            "/spec-builder/entity/Document/field/0",
            data={
                "name": "identifier",
                "field_type": "string",
                "required": "true",
                "description": "Document identifier",
                "ontology_term": "",
                "codename": "",
                "items": "",
                "parent_ref": "",
                "pattern": "",
                "min_length": "",
                "max_length": "",
                "minimum": "",
                "maximum": "",
                "enum_values": "",
            },
        )

        client.post(
            "/spec-builder/entity/Document/field",
            data={"name": "title", "field_type": "string"},
        )

        # Preview
        response = client.get("/spec-builder/preview")
        assert "simple-spec" in response.text
        assert "Document:" in response.text
        assert "identifier" in response.text
        assert "title" in response.text

    def test_clone_and_modify_workflow(self, client):
        """Test cloning a spec and modifying it."""
        # Clone MIAPPE
        client.get("/spec-builder/clone/miappe/1.1")

        # Modify metadata
        client.post(
            "/spec-builder/profile-metadata",
            data={
                "name": "custom-miappe",
                "version": "1.0",
                "display_name": "Custom MIAPPE",
                "description": "Modified MIAPPE spec",
                "ontology": "PPEO",
                "root_entity": "Investigation",
            },
        )

        # Add a new entity
        client.post("/spec-builder/entity", data={"name": "CustomEntity"})
        client.post(
            "/spec-builder/entity/CustomEntity/field",
            data={"name": "custom_field", "field_type": "string"},
        )

        # Preview should show modifications
        response = client.get("/spec-builder/preview")
        assert "custom-miappe" in response.text
        assert "CustomEntity:" in response.text
        assert "custom_field" in response.text
        # Should still have original entities
        assert "Investigation:" in response.text
