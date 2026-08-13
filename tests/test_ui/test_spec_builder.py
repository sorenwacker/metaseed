"""Tests for the Builder UI.

Tests helpers and routes for creating/editing ProfileSpec specifications.
"""

import re
from pathlib import Path

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
from metaseed.ui.app import create_app
from metaseed.ui.helpers.spec_builder_helpers import (
    clone_spec,
    create_empty_spec,
    list_available_templates,
    spec_to_yaml,
    validate_entity_name,
    validate_field_name,
)
from metaseed.ui.spec_builder import SpecBuilderState
from metaseed.ui.state import AppState


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
        assert spec.version == "0.1"
        assert spec.name == ""
        assert spec.entities == {}
        assert spec.validation_rules == []

    def test_clone_spec_miappe(self):
        """clone_spec creates independent copy of MIAPPE spec."""
        spec = clone_spec("miappe", "1.1")
        assert isinstance(spec, ProfileSpec)
        assert spec.name == "miappe"
        # A clone keeps the source version; it is a derivative of 1.1 until the
        # author sets a new one. Profile versions are MAJOR.MINOR, so a draft
        # cannot carry a marker suffix and still load back.
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

    def test_spec_to_yaml_does_not_mutate_global_yaml_registry(
        self, sample_spec
    ) -> None:
        """spec_to_yaml must not register a global str representer side effect."""
        import yaml

        before = yaml.Dumper.yaml_representers.get(str)
        spec_to_yaml(sample_spec)
        after = yaml.Dumper.yaml_representers.get(str)
        assert before is after

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
        assert validate_field_name("field-name") is None  # hyphens allowed

    def test_validate_field_name_invalid(self):
        """validate_field_name returns error for invalid names."""
        assert validate_field_name("") is not None
        assert validate_field_name("UniqueId") is not None  # PascalCase
        assert validate_field_name("123field") is not None  # starts with number


class TestSpecBuilderRoutes:
    """Tests for spec builder routes."""

    def test_spec_builder_index_start(self, client):
        """Spec builder index shows start options when no spec in progress."""
        response = client.get("/spec-builder")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Start from Scratch" in response.text
        assert "Clone Template" in response.text

    def test_new_spec(self, client):
        """Creating new spec initializes empty spec."""
        response = client.get("/spec-builder/new")
        assert response.status_code == 200
        assert "Builder" in response.text
        # Should show ERD editor view
        assert "Profile" in response.text
        assert "Toolbox" in response.text

    def test_clone_spec(self, client):
        """Cloning spec creates copy of existing."""
        response = client.get("/spec-builder/clone/miappe/1.1")
        assert response.status_code == 200
        assert "Builder" in response.text
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

    def test_rename_entity(self, client):
        """Rename entity."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "OldName"})
        response = client.put(
            "/spec-builder/entity/OldName",
            data={"name": "NewName", "description": "", "ontology_term": ""},
        )
        assert response.status_code == 200
        assert "NewName" in response.text
        # Verify old name is gone
        response = client.get("/spec-builder/preview")
        assert "NewName:" in response.text
        assert "OldName:" not in response.text

    def test_rename_entity_updates_references(self, client):
        """Rename entity updates items, reference, and parent_ref in other entities."""
        client.get("/spec-builder/new")
        # Create two entities
        client.post("/spec-builder/entity", data={"name": "Parent"})
        client.post("/spec-builder/entity", data={"name": "Child"})
        # Add field in Child that references Parent
        client.post(
            "/spec-builder/entity/Child/field",
            data={"name": "parent_items", "field_type": "list", "items": "Parent"},
        )
        # Rename Parent to NewParent
        client.put(
            "/spec-builder/entity/Parent",
            data={"name": "NewParent", "description": "", "ontology_term": ""},
        )
        # Verify items was updated in Child
        response = client.get("/spec-builder/preview")
        assert "items: NewParent" in response.text
        assert "items: Parent" not in response.text

    def test_rename_entity_updates_validation_rules(self, client) -> None:
        """Renaming an entity updates applies_to and reference in rules.

        Exercises the route's delegation to SpecBuilder.rename_entity; the
        cascade itself is unit-tested in tests/test_specs/test_builder.py.
        """
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Study"})
        client.post("/spec-builder/entity", data={"name": "ObservationUnit"})
        # Add a rule and configure it to reference Study / apply to ObservationUnit.
        client.post("/spec-builder/validation-rule", data={"name": "ou_study_ref"})
        client.put(
            "/spec-builder/validation-rule/0",
            data={
                "name": "ou_study_ref",
                "applies_to": "ObservationUnit",
                "reference": "Study.unique_id",
            },
        )

        client.put(
            "/spec-builder/entity/Study",
            data={"name": "Investigation", "description": "", "ontology_term": ""},
        )
        preview = client.get("/spec-builder/preview").text
        assert "reference: Investigation.unique_id" in preview
        assert "Study.unique_id" not in preview

        client.put(
            "/spec-builder/entity/ObservationUnit",
            data={"name": "ObsUnit", "description": "", "ontology_term": ""},
        )
        preview = client.get("/spec-builder/preview").text
        assert "applies_to: ObsUnit" in preview

    def test_set_seek_role_persists_and_reselects(self, client):
        """Selecting a SEEK role serializes to YAML and re-selects on reopen."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sampling"})
        resp = client.put(
            "/spec-builder/entity/Sampling",
            data={
                "name": "Sampling",
                "description": "",
                "ontology_term": "",
                "seek_role": "ObservationUnit",
            },
        )
        assert resp.status_code == 200
        assert 'value="ObservationUnit" selected' in resp.text  # editor re-selects
        assert "role: ObservationUnit" in client.get("/spec-builder/preview").text

    def test_update_entity_without_seek_role_preserves_it(self, client):
        """A PUT that omits seek_role (e.g. a rename form) must not wipe the role."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sampling"})
        client.put(
            "/spec-builder/entity/Sampling",
            data={"name": "Sampling", "seek_role": "Sample"},
        )
        client.put(  # no seek_role field this time
            "/spec-builder/entity/Sampling",
            data={"name": "Sampling", "description": "d", "ontology_term": ""},
        )
        assert "role: Sample" in client.get("/spec-builder/preview").text

    def test_seek_role_none_clears_it(self, client):
        """A present-but-blank seek_role clears a previously set role.

        The browser's ``<select>`` "— none —" submits ``seek_role=`` (present but
        empty); httpx drops empty-string form values, so send a whitespace value
        which ``.strip()`` reduces to the same empty-and-therefore-clear branch.
        """
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sampling"})
        client.put(
            "/spec-builder/entity/Sampling",
            data={"name": "Sampling", "seek_role": "Sample"},
        )
        client.put(
            "/spec-builder/entity/Sampling",
            data={"name": "Sampling", "seek_role": " "},  # "— none —" (blank)
        )
        assert "role:" not in client.get("/spec-builder/preview").text

    def test_add_list_field_creates_back_reference(self, client):
        """Adding a list field auto-creates back-reference in target entity."""
        client.get("/spec-builder/new")
        # Create parent and child entities
        client.post("/spec-builder/entity", data={"name": "Investigation"})
        client.post("/spec-builder/entity", data={"name": "Study"})
        # Add studies list to Investigation
        client.post(
            "/spec-builder/entity/Investigation/field",
            data={"name": "studies", "field_type": "list", "items": "Study"},
        )
        # Verify back-reference was created in Study
        response = client.get("/spec-builder/preview")
        preview = response.text
        # Study should have investigation_id with reference
        assert "investigation_id" in preview
        assert "reference: Investigation.identifier" in preview
        # Investigation should have identifier field
        assert "identifier" in preview

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

    def test_move_field_up(self, client):
        """Move field up in the list."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "first_field", "field_type": "string"},
        )
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "second_field", "field_type": "string"},
        )
        # Move second field up
        response = client.post("/spec-builder/entity/TestEntity/field/1/move-up")
        assert response.status_code == 200
        # second_field should now be first (check order in HTML)
        first_pos = response.text.find("second_field")
        second_pos = response.text.find("first_field")
        assert first_pos < second_pos

    def test_move_field_down(self, client):
        """Move field down in the list."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "first_field", "field_type": "string"},
        )
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "second_field", "field_type": "string"},
        )
        # Move first field down
        response = client.post("/spec-builder/entity/TestEntity/field/0/move-down")
        assert response.status_code == 200
        # first_field should now be second
        first_pos = response.text.find("second_field")
        second_pos = response.text.find("first_field")
        assert first_pos < second_pos

    def test_move_field_up_at_top_noop(self, client):
        """Moving first field up does nothing."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "TestEntity"})
        client.post(
            "/spec-builder/entity/TestEntity/field",
            data={"name": "only_field", "field_type": "string"},
        )
        response = client.post("/spec-builder/entity/TestEntity/field/0/move-up")
        assert response.status_code == 200
        assert "only_field" in response.text

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

    def test_delete_user_spec_builtin_forbidden(self, client):
        """Cannot delete built-in specs."""
        response = client.delete("/spec-builder/user-spec/miappe/1.2")
        assert response.status_code == 403
        assert "built-in" in response.json()["detail"].lower()


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

    def test_entity_persisted_after_creation(self, client):
        """Test that newly created entities are persisted in spec state."""
        # Start new spec
        client.get("/spec-builder/new")

        # Create first entity
        response = client.post("/spec-builder/entity", data={"name": "FirstEntity"})
        assert response.status_code == 200
        assert "FirstEntity" in response.text

        # Create second entity
        response = client.post("/spec-builder/entity", data={"name": "SecondEntity"})
        assert response.status_code == 200
        assert "SecondEntity" in response.text

        # Verify both entities appear in preview
        response = client.get("/spec-builder/preview")
        assert response.status_code == 200
        assert "FirstEntity:" in response.text
        assert "SecondEntity:" in response.text

    def test_entity_persisted_in_graph_data(self, client):
        """Test that entities appear in graph-data endpoint."""
        # Start new spec
        client.get("/spec-builder/new")

        # Create entity
        client.post("/spec-builder/entity", data={"name": "GraphEntity"})

        # Check graph-data endpoint
        response = client.get("/spec-builder/graph-data")
        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        assert "GraphEntity" in data["entities"]

    def test_entity_with_fields_persisted(self, client):
        """Test that entity with fields is correctly persisted."""
        # Start new spec
        client.get("/spec-builder/new")

        # Create entity
        client.post("/spec-builder/entity", data={"name": "FieldEntity"})

        # Add field
        response = client.post(
            "/spec-builder/entity/FieldEntity/field",
            data={"name": "test_field", "field_type": "string"},
        )
        assert response.status_code == 200
        assert "test_field" in response.text

        # Verify in preview
        response = client.get("/spec-builder/preview")
        assert "FieldEntity:" in response.text
        assert "test_field" in response.text


class TestSpecBuilderImport:
    """Tests for spec import functionality."""

    def test_import_valid_yaml(self, client):
        """Import a valid YAML spec file."""
        yaml_content = """
version: '1.0'
name: imported-spec
display_name: Imported Spec
description: A spec imported from YAML
root_entity: Document
entities:
  Document:
    description: A document entity
    fields:
      - name: identifier
        type: string
        required: true
        description: Unique identifier
"""
        response = client.post(
            "/spec-builder/import",
            files={"file": ("test-spec.yaml", yaml_content, "application/x-yaml")},
            follow_redirects=False,
        )
        # Should redirect to spec builder
        assert response.status_code == 303

        # Verify spec was loaded
        response = client.get("/spec-builder/preview")
        assert "imported-spec" in response.text
        assert "Document:" in response.text
        assert "identifier" in response.text

    def test_import_invalid_extension(self, client):
        """Reject files without .yaml or .yml extension."""
        response = client.post(
            "/spec-builder/import",
            files={"file": ("test.txt", "some content", "text/plain")},
        )
        assert response.status_code == 400
        assert "YAML file" in response.json()["detail"]

    def test_import_invalid_yaml_syntax(self, client):
        """Reject files with invalid YAML syntax."""
        invalid_yaml = "{ invalid: yaml: content"
        response = client.post(
            "/spec-builder/import",
            files={"file": ("bad.yaml", invalid_yaml, "application/x-yaml")},
        )
        assert response.status_code == 400
        assert "Invalid YAML" in response.json()["detail"]

    def test_import_invalid_spec_structure(self, client):
        """Reject YAML that doesn't match ProfileSpec schema."""
        invalid_spec = """
not_a_valid_field: true
random_data: 123
"""
        response = client.post(
            "/spec-builder/import",
            files={"file": ("invalid.yaml", invalid_spec, "application/x-yaml")},
        )
        assert response.status_code == 400
        assert "Failed to parse" in response.json()["detail"]

    def test_import_non_mapping_yaml_keeps_specific_detail(self, client):
        """A non-mapping root must surface its own message, not a re-wrapped one.

        The intentional HTTPException is raised inside the try block and must
        not be re-wrapped by the broad ``except Exception`` into a
        ``Failed to parse spec: 400: ...`` message.
        """
        non_mapping = "- just\n- a\n- list\n"
        response = client.post(
            "/spec-builder/import",
            files={"file": ("list.yaml", non_mapping, "application/x-yaml")},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail == "Invalid YAML: root must be a mapping"
        assert "Failed to parse" not in detail

    def test_import_does_not_overload_template_source(self):
        """Import must leave template_source as a (profile, version) tuple or None.

        template_source is consumed by the template via index access, so it must
        never be set to a free-form string on import.
        """
        state = AppState()
        app = create_app(state)
        client = TestClient(app)

        yaml_content = """
version: '1.0'
name: imported-spec
display_name: Imported Spec
description: A spec imported from YAML
root_entity: Document
entities:
  Document:
    description: A document entity
    fields:
      - name: identifier
        type: string
        required: true
        description: Unique identifier
"""
        response = client.post(
            "/spec-builder/import",
            files={"file": ("test-spec.yaml", yaml_content, "application/x-yaml")},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert state.spec_builder is not None
        assert state.spec_builder.template_source is None


class TestSpecBuilderApplyYaml:
    """Tests for applying edited YAML to the current spec."""

    def test_apply_non_mapping_yaml_keeps_specific_detail(self, client):
        """A non-mapping root must keep its own error detail, not a re-wrapped one."""
        client.get("/spec-builder/new")
        response = client.post(
            "/spec-builder/apply-yaml",
            content="- just\n- a\n- list\n",
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail == "Invalid YAML: root must be a mapping"
        assert "Failed to parse" not in detail


class TestSpecBuilderMarkers:
    """The spec-builder field form exposes the spec_version 0.6 markers."""

    def test_owns_and_metadata_markers_persist_through_the_field_form(self, client):
        """owns / is_identifier / is_label / tier / label / unit / example / options
        are editable in the builder and survive a field update."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Investigation"})
        client.post("/spec-builder/entity", data={"name": "Study"})
        client.post(
            "/spec-builder/entity/Investigation/field",
            data={"name": "studies", "field_type": "list", "items": "Study"},
        )

        resp = client.put(
            "/spec-builder/entity/Investigation/field/0",
            data={
                "name": "studies",
                "field_type": "list",
                "items": "Study",
                "owns": "true",
                "tier": "recommended",
                "label": "Studies",
                "unit": "",
                "example": "",
                "options": "",
            },
        )
        assert resp.status_code == 200

        preview = client.get("/spec-builder/preview").text
        assert "owns: true" in preview
        assert "tier: recommended" in preview
        assert "label: Studies" in preview

    def test_unset_markers_do_not_serialize_their_falsey_form(self, client):
        """An unchecked owns must not write ``owns: false`` (no churn)."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sample"})
        client.post(
            "/spec-builder/entity/Sample/field",
            data={"name": "name", "field_type": "string"},
        )
        client.put(
            "/spec-builder/entity/Sample/field/0",
            data={"name": "name", "field_type": "string"},
        )
        preview = client.get("/spec-builder/preview").text
        assert "owns: false" not in preview
        assert "is_identifier: false" not in preview


class TestFieldFormReuse:
    """The field form is reusable by a consumer that mounts it elsewhere.

    metaseed-hub needs this template per draft under a ``/hub`` prefix. It
    forked the file instead, and the fork silently lost all 31 guidance
    tooltips. Keeping the template free of one app's URL scheme is what lets a
    consumer render it instead of copying it.
    """

    @staticmethod
    def _field_form(client) -> str:
        """Render the field editor for a plain string field."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sample"})
        client.post(
            "/spec-builder/entity/Sample/field",
            data={"name": "title", "field_type": "string"},
        )
        return client.get("/spec-builder/entity/Sample/field/0").text

    def test_cancel_falls_back_to_the_builtin_entity_url(self, client):
        """With no entity_url supplied the library UI is unchanged."""
        assert 'hx-get="/spec-builder/entity/Sample"' in self._field_form(client)

    def test_the_template_names_no_other_absolute_url(self, client):
        """Every other action routes through the JS config.url, not a literal.

        A second hardcoded path would have to be patched by each consumer, which
        is how the fork started.
        """
        html = self._field_form(client)
        literals = re.findall(r'hx-(?:get|post|put|delete)="(/[^"]*)"', html)
        assert literals == ["/spec-builder/entity/Sample"], literals

    def test_a_consumer_can_supply_its_own_entity_url(self):
        """The cancel target is whatever the caller passes."""
        from fastapi.templating import Jinja2Templates

        from metaseed.ui.app import TEMPLATES_DIR

        templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
        field = FieldSpec(name="title", type=FieldType.STRING)
        html = templates.get_template("spec_builder/partials/field_form.html").render(
            spec=ProfileSpec(
                version="1.0",
                name="p",
                display_name="P",
                description="d",
                ontology="T",
                root_entity="Sample",
                entities={"Sample": EntityDefSpec(description="d", fields=[field])},
            ),
            entity_name="Sample",
            field=field,
            field_idx=0,
            field_types=[t.value for t in FieldType],
            entity_url="/hub/spec-builder/abc123/entity/Sample",
        )
        assert 'hx-get="/hub/spec-builder/abc123/entity/Sample"' in html
        assert "/spec-builder/entity/Sample" not in html.replace(
            "/hub/spec-builder/abc123/entity/Sample", ""
        )

    def test_guidance_is_delivered_by_a_visible_marker(self) -> None:
        """A native tooltip is not a reliable way to reach the user.

        It stays invisible until hovered for about a second, never appears on
        touch, and on some machines does not render at all -- so help written
        into a profile simply never arrived. The builder converts every ``title``
        into a focusable "?" beside the label, with the bubble on ``body`` so the
        panels, which all clip their overflow, cannot cut it off.
        """
        from metaseed.ui.app import STATIC_DIR

        script = (Path(STATIC_DIR) / "js" / "help-markers.js").read_text()
        assert "removeAttribute('title')" in script, "a second, native copy would show"
        assert "document.body.appendChild" in script, "the bubble must escape clipping"
        assert "htmx:afterSwap" in script, "a partial loaded later must be covered too"

        css = (Path(STATIC_DIR) / "css" / "style.css").read_text()
        assert ".help-marker" in css
        assert ".help-bubble" in css

    def test_every_constraint_control_carries_guidance(self, client):
        """The tooltips are the reason a consumer should reuse rather than copy.

        The hub's fork dropped all of them, leaving users to guess what Pattern,
        Unique Within or Tier mean.
        """
        html = self._field_form(client)
        assert html.count('title="') >= 31, html.count('title="')


class TestSpecBuilderDcat:
    """The DCAT property is editable in the builder.

    ``FieldSpec.dcat`` has existed since the dcat support landed, but no builder
    control ever set it, so the only way to reach it was to hand-edit YAML or use
    a consumer that forked the field form to add its own input.
    """

    def test_the_dcat_property_persists_through_the_field_form(self, client):
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sample"})
        client.post(
            "/spec-builder/entity/Sample/field",
            data={"name": "title", "field_type": "string"},
        )

        resp = client.put(
            "/spec-builder/entity/Sample/field/0",
            data={"name": "title", "field_type": "string", "dcat": "dct:title"},
        )
        assert resp.status_code == 200

        assert "dcat: dct:title" in client.get("/spec-builder/preview").text

    def test_an_empty_dcat_does_not_serialize(self, client):
        """A blank box must clear the property, not write an empty string."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sample"})
        client.post(
            "/spec-builder/entity/Sample/field",
            data={"name": "title", "field_type": "string"},
        )
        client.put(
            "/spec-builder/entity/Sample/field/0",
            data={"name": "title", "field_type": "string", "dcat": ""},
        )
        assert "dcat:" not in client.get("/spec-builder/preview").text

    def test_the_field_form_offers_a_dcat_control(self, client):
        """Without the input the property is unreachable from the UI."""
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Sample"})
        client.post(
            "/spec-builder/entity/Sample/field",
            data={"name": "title", "field_type": "string"},
        )
        html = client.get("/spec-builder/entity/Sample/field/0").text
        assert 'name="dcat"' in html


class TestReferenceScopeInTheFieldEditor:
    """A reference that resolves outside the dataset, set from the UI."""

    def _field(self, client) -> None:
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "Taxon"})
        client.post(
            "/spec-builder/entity/Taxon/field",
            data={"name": "taxonID", "field_type": "string"},
        )
        client.post(
            "/spec-builder/entity/Taxon/field",
            data={"name": "acceptedNameUsageID", "field_type": "string"},
        )

    def _save(self, client, **extra):
        data = {
            "name": "acceptedNameUsageID",
            "field_type": "string",
            "reference": "Taxon.taxonID",
        }
        data.update(extra)
        return client.put("/spec-builder/entity/Taxon/field/1", data=data)

    def test_the_editor_offers_it(self, client) -> None:
        self._field(client)

        form = client.get("/spec-builder/entity/Taxon/field/1").text

        assert 'data-testid="reference-scope"' in form

    def test_it_is_saved(self, client) -> None:
        self._field(client)

        self._save(client, reference_scope="external")

        assert "reference_scope: external" in client.get("/spec-builder/preview").text

    def test_the_default_is_not_written_back(self, client) -> None:
        """`dataset` is what an absent key already means, so writing it would
        record in the content hash which way it happened to be said."""
        self._field(client)

        self._save(client, reference_scope="")

        assert "reference_scope" not in client.get("/spec-builder/preview").text
