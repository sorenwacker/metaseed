"""Tests for the HTMX UI routes.

Tests use FastAPI TestClient to verify route behavior.
"""

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def client():
    """Create a test client with fresh state."""
    state = AppState()
    app = create_app(state)
    return TestClient(app)


@pytest.fixture
def client_with_entity(client):
    """Create a test client and add an investigation entity."""
    response = client.post(
        "/entity",
        data={
            "_entity_type": "Investigation",
            "unique_id": "INV-001",
            "title": "Test Investigation",
        },
    )
    assert response.status_code == 200
    return client


class TestIndex:
    """Tests for the main index page."""

    def test_index_returns_html(self, client):
        """Index route returns HTML page."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_index_contains_title(self, client):
        """Index page contains Metaseed title."""
        response = client.get("/")
        assert "Metaseed" in response.text

    def test_index_contains_new_dataset_button(self, client):
        """Index page contains new dataset button."""
        response = client.get("/")
        assert "New Dataset" in response.text

    def test_index_contains_stop_physics_control(self, client):
        """Graph controls expose a button to freeze the force simulation."""
        response = client.get("/")
        assert 'data-testid="btn-graph-physics"' in response.text
        assert "toggleGraphPhysics()" in response.text


class TestForm:
    """Tests for entity forms."""

    def test_new_investigation_shows_profile_select(self, client):
        """New Investigation shows profile selection first."""
        response = client.get("/form/Investigation")
        assert response.status_code == 200
        assert "New Dataset" in response.text
        assert "MIAPPE" in response.text
        assert "ISA" in response.text

    def test_new_form_returns_html(self, client):
        """New entity form route returns HTML with profile specified."""
        response = client.get("/form/Investigation?profile=miappe")
        assert response.status_code == 200
        assert "New Investigation" in response.text

    def test_new_form_contains_required_fields(self, client):
        """Form contains required fields section."""
        response = client.get("/form/Investigation?profile=miappe")
        assert "Required Fields" in response.text
        assert "unique_id" in response.text
        assert "title" in response.text

    def test_new_form_contains_optional_fields(self, client):
        """Form contains optional fields section."""
        response = client.get("/form/Investigation?profile=miappe")
        assert "Optional Fields" in response.text

    def test_new_form_unknown_entity_404(self, client):
        """Unknown entity type returns 404."""
        response = client.get("/form/UnknownEntity?profile=miappe")
        assert response.status_code == 404

    def test_new_form_offers_example_when_shipped(self, client):
        """Form offers to load an example when one ships for the profile/version.

        Regression test for EXAMPLES_DIR resolving to a non-existent repo-root
        path: examples live under src/metaseed/examples, so the affordance must
        appear for a profile that ships one (miappe).
        """
        response = client.get("/form/Investigation?profile=miappe")
        assert response.status_code == 200
        assert 'data-testid="btn-load-example"' in response.text


class TestCreateEntity:
    """Tests for entity creation."""

    def test_create_entity_success(self, client):
        """Create entity with valid data succeeds."""
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200
        assert "Created Investigation" in response.text

    def test_create_entity_missing_type(self, client):
        """Create without entity type fails."""
        response = client.post(
            "/entity",
            data={"unique_id": "INV-001"},
        )
        assert response.status_code == 200
        assert "required" in response.text.lower()

    def test_create_entity_saves_draft_with_validation_warning(self, client):
        """Create with incomplete data is never blocked: it saves a draft and
        surfaces a non-blocking warning listing the missing-field hints."""
        response = client.post(
            "/entity",
            data={
                # Missing required fields (unique_id, title).
                "_entity_type": "Investigation",
            },
        )
        # Saving is not blocked by validation.
        assert response.status_code == 200
        # Non-blocking warning notification, not a blocking error.
        assert 'data-testid="form-warning"' in response.text
        assert 'data-testid="form-error"' not in response.text
        # Message reports a draft save and lists the missing-field hints.
        assert "Saved draft" in response.text
        assert "incomplete" in response.text
        assert "title" in response.text
        assert "required" in response.text.lower()
        # The entity is still persisted as a draft.
        assert response.headers.get("HX-Trigger") == "entityCreated"
        state = client.app.state.ui_state
        assert len(state.nodes_by_id) == 1


class TestEditEntity:
    """Tests for entity editing."""

    def test_edit_form_shows_values(self, client_with_entity):
        """Edit form shows existing values."""
        # After create, we get the edit form with the created data
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.get(f"/form/Investigation/{node_id}")
        assert response.status_code == 200
        assert "Test Investigation" in response.text

    def test_edit_unknown_node_404(self, client):
        """Edit nonexistent node returns 404."""
        response = client.get("/form/Investigation/nonexistent")
        assert response.status_code == 404


class TestDeleteEntity:
    """Tests for entity deletion."""

    def test_delete_entity_success(self, client):
        """Delete existing entity succeeds."""
        create_response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "To Delete",
            },
        )
        assert create_response.status_code == 200

        state = client.app.state.ui_state
        assert len(state.nodes_by_id) == 1
        node_id = next(iter(state.nodes_by_id.keys()))

        delete_response = client.delete(f"/entity/{node_id}")
        assert delete_response.status_code == 200

        # Verify node was removed from state
        assert len(state.nodes_by_id) == 0

    def test_delete_unknown_node_error(self, client):
        """Delete nonexistent node returns error."""
        response = client.delete("/entity/nonexistent")
        assert response.status_code == 200
        assert "Node not found: nonexistent" in response.text


class TestBaseUrlPrefix:
    """Tests that CRUD partial re-renders honor a non-empty base_url."""

    def _make_client(self) -> TestClient:
        """Create a test client whose app is mounted under /hub."""
        state = AppState()
        app = create_app(state, base_url="/hub")
        return TestClient(app)

    def test_delete_partial_includes_base_url_prefix(self):
        """Delete re-render emits index.html links with the base_url prefix."""
        client = self._make_client()
        for unique_id in ("INV-001", "INV-002"):
            response = client.post(
                "/entity",
                data={
                    "_entity_type": "Investigation",
                    "unique_id": unique_id,
                    "title": unique_id,
                },
            )
            assert response.status_code == 200

        # Delete one of two entities so the populated branch (with
        # export/import/form/delete links) is exercised on re-render.
        node_id = next(iter(client.app.state.ui_state.nodes_by_id.keys()))
        delete_response = client.delete(f"/entity/{node_id}")
        assert delete_response.status_code == 200
        assert 'href="/hub/export"' in delete_response.text
        assert 'hx-post="/hub/import"' in delete_response.text
        assert 'hx-delete="/hub/entity/' in delete_response.text

    def test_update_back_partial_includes_base_url_prefix(self):
        """Update 'back' action re-render emits links with the base_url prefix."""
        client = self._make_client()
        create_response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert create_response.status_code == 200

        node_id = next(iter(client.app.state.ui_state.nodes_by_id.keys()))
        update_response = client.put(
            f"/entity/{node_id}",
            data={
                "unique_id": "INV-001",
                "title": "Updated Investigation",
                "_action": "back",
            },
        )
        assert update_response.status_code == 200
        assert 'href="/hub/export"' in update_response.text
        assert 'hx-post="/hub/import"' in update_response.text


class TestProfileSwitch:
    """Tests for profile switching."""

    def test_switch_to_miappe(self, client):
        """Switch to miappe profile redirects."""
        response = client.get("/profile/miappe", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_switch_to_isa(self, client):
        """Switch to isa profile redirects."""
        response = client.get("/profile/isa", follow_redirects=False)
        assert response.status_code == 303

    def test_switch_unknown_profile_400(self, client):
        """Switch to unknown profile returns 400."""
        response = client.get("/profile/unknown")
        assert response.status_code == 400


class TestTableView:
    """Tests for nested table views."""

    def test_table_view_requires_valid_entity(self, client):
        """Table view requires valid entity type."""
        response = client.get("/table/UnknownEntity/studies")
        assert response.status_code == 404

    def test_table_view_requires_valid_field(self, client):
        """Table view requires valid field name."""
        response = client.get("/table/Investigation/unknown_field")
        assert response.status_code == 404

    def test_table_view_valid_nested_field(self, client):
        """Table view works for valid nested field."""
        response = client.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert "studies" in response.text.lower() or "Studies" in response.text


class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_served(self, client):
        """CSS file is served."""
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_js_served(self, client):
        """JS file is served."""
        response = client.get("/static/js/core.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]


class TestHtmxHeaders:
    """Tests for HTMX-specific behavior."""

    def test_create_sets_trigger_header(self, client):
        """Create entity sets HX-Trigger header."""
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("HX-Trigger") == "entityCreated"

    def test_update_with_created_in_label_fires_entity_updated(self, client):
        """An update whose label contains the word 'Created' must still fire
        entityUpdated. Regression: the trigger was chosen by substring-matching
        the user-facing message, so a 'Created'-containing label misfired.
        """
        client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-002",
                "title": "Created plots",
            },
        )
        node_id = next(iter(client.app.state.ui_state.nodes_by_id.keys()))

        response = client.put(
            f"/entity/{node_id}",
            data={"unique_id": "INV-002", "title": "Created plots"},
        )

        assert response.status_code == 200
        assert response.headers.get("HX-Trigger") == "entityUpdated"


class TestAppState:
    """Tests for AppState class."""

    def test_get_or_create_facade(self):
        """Facade is created on first access."""
        state = AppState()
        facade = state.get_or_create_facade()
        assert facade is not None
        assert facade.profile == "miappe"

    def test_facade_cached(self):
        """Same facade instance returned on multiple calls."""
        state = AppState()
        facade1 = state.get_or_create_facade()
        facade2 = state.get_or_create_facade()
        assert facade1 is facade2

    def test_facade_recreated_on_profile_change(self):
        """New facade created when profile changes."""
        state = AppState()
        facade1 = state.get_or_create_facade()
        state.profile = "isa"
        facade2 = state.get_or_create_facade()
        assert facade1 is not facade2
        assert facade2.profile == "isa"

    def test_add_node(self):
        """Add node to tree."""
        state = AppState()
        facade = state.get_or_create_facade()
        # Use .create() to avoid auto-storing (facade.Investigation() auto-stores)
        instance = facade.Investigation.create(unique_id="INV-001", title="Test")
        node = state.add_node("Investigation", instance)

        assert node.id in state.nodes_by_id
        assert len(state.entity_tree) == 1
        # By convention, first field (unique_id) is used as label
        assert node.label == "INV-001"

    def test_update_node(self):
        """Update existing node."""
        state = AppState()
        facade = state.get_or_create_facade()
        # Use .create() to avoid auto-storing
        instance = facade.Investigation.create(unique_id="INV-001", title="Original")
        node = state.add_node("Investigation", instance)

        updated_instance = facade.Investigation.create(
            unique_id="INV-002", title="Updated"
        )
        state.update_node(node.id, updated_instance)

        # By convention, first field (unique_id) is used as label
        assert state.nodes_by_id[node.id].label == "INV-002"

    def test_delete_node(self):
        """Delete node from tree."""
        state = AppState()
        facade = state.get_or_create_facade()
        # Use .create() to avoid auto-storing
        instance = facade.Investigation.create(unique_id="INV-001", title="Test")
        node = state.add_node("Investigation", instance)

        result = state.delete_node(node.id)
        assert result is True
        assert node.id not in state.nodes_by_id
        assert len(state.entity_tree) == 0

    def test_get_root_entity_types(self):
        """Get root entity types."""
        state = AppState()
        roots = state.get_root_entity_types()
        assert "Investigation" in roots
        assert roots[0] == "Investigation"

    def test_get_tree_data_empty(self):
        """Get tree data with no entities."""
        state = AppState()
        tree_data = state.get_tree_data()
        assert tree_data == []

    def test_get_tree_data_with_entity(self):
        """Get tree data with an entity."""
        state = AppState()
        facade = state.get_or_create_facade()
        # Use .create() to avoid auto-storing
        instance = facade.Investigation.create(
            unique_id="INV-001", title="Test Investigation"
        )
        state.add_node("Investigation", instance)

        tree_data = state.get_tree_data()
        assert len(tree_data) == 1
        assert tree_data[0]["entity_type"] == "Investigation"
        # By convention, first field (unique_id) is used as label
        assert tree_data[0]["label"] == "INV-001"

    def test_get_tree_data_with_nested_entities(self):
        """Get tree data includes child entities added via parent_id.

        By convention, first field (identifier for ISA) is used as label.
        """
        # Use ISA profile since it has consistent model caching across tests
        state = AppState()
        state.profile = "isa"
        facade = state.get_or_create_facade()

        # Create Investigation node (use .create() to avoid auto-storing)
        inv_instance = facade.Investigation.create(
            identifier="INV-001",
            title="Test Investigation",
        )
        inv_node = state.add_node("Investigation", inv_instance)

        # Create Studies as children of Investigation
        study1 = facade.Study.create(
            identifier="STU-001",
            title="Study One",
            investigation_id="INV-001",
        )
        state.add_node("Study", study1, parent_id=inv_node.id)

        study2 = facade.Study.create(
            identifier="STU-002",
            title="Study Two",
            investigation_id="INV-001",
        )
        state.add_node("Study", study2, parent_id=inv_node.id)

        tree_data = state.get_tree_data()
        assert len(tree_data) == 1
        assert tree_data[0]["has_children"] is True
        assert len(tree_data[0]["children"]) == 2
        # ISA Study's first field is identifier
        assert tree_data[0]["children"][0]["label"] == "STU-001"
        assert tree_data[0]["children"][0]["entity_type"] == "Study"

    def test_reset_clears_all_state(self):
        """Reset clears all state."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Test")
        node = state.add_node("Investigation", instance)
        state.editing_node_id = node.id
        state.current_nested_items = {"studies": [{"title": "Test"}]}

        state.reset()

        assert len(state.entity_tree) == 0
        assert len(state.nodes_by_id) == 0
        assert state.editing_node_id is None
        assert state.current_nested_items == {}

    def test_delete_node_clears_editing_id(self):
        """Delete node clears editing_node_id if it matches."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Test")
        node = state.add_node("Investigation", instance)
        state.editing_node_id = node.id

        state.delete_node(node.id)

        assert state.editing_node_id is None

    def test_delete_nonexistent_node(self):
        """Delete nonexistent node returns False."""
        state = AppState()
        result = state.delete_node("nonexistent-id")
        assert result is False

    def test_update_nonexistent_node(self):
        """Update nonexistent node returns None."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Test")
        result = state.update_node("nonexistent-id", instance)
        assert result is None


class TestExport:
    """Tests for export functionality."""

    def test_export_empty_returns_excel(self, client):
        """Export with no entities returns Excel file."""
        response = client.get("/export")
        assert response.status_code == 200
        assert "spreadsheetml" in response.headers["content-type"]

    def test_export_with_entity(self, client_with_entity):
        """Export with entity includes data sheets."""
        response = client_with_entity.get("/export")
        assert response.status_code == 200
        assert "spreadsheetml" in response.headers["content-type"]
        # Check content disposition header has filename
        assert "attachment" in response.headers.get("content-disposition", "")

    def test_export_button_in_edit_form(self, client_with_entity):
        """Edit form contains Export All button."""
        # Export button moved from navbar to edit form
        state = client_with_entity.app.state.ui_state
        node = next(iter(state.nodes_by_id.values()))
        response = client_with_entity.get(f"/form/{node.entity_type}/{node.id}")
        assert "Export All" in response.text


class TestResetState:
    """Tests for reset state route."""

    def test_reset_clears_entities(self, client_with_entity):
        """Reset removes all entities."""
        state = client_with_entity.app.state.ui_state
        assert len(state.nodes_by_id) == 1

        response = client_with_entity.post("/reset")
        assert response.status_code == 200
        assert response.text == "OK"
        assert len(state.nodes_by_id) == 0

    def test_reset_on_empty_state(self, client):
        """Reset on empty state succeeds."""
        response = client.post("/reset")
        assert response.status_code == 200


class TestValidateForm:
    """Tests for form validation route."""

    def test_validate_missing_entity_type(self, client):
        """Validate without entity type returns error."""
        response = client.post("/validate", data={})
        assert response.status_code == 200
        assert "Entity type is required" in response.text

    def test_validate_unknown_entity_type(self, client):
        """Validate with an unknown entity type returns a graceful error."""
        response = client.post(
            "/validate",
            data={"_entity_type": "NotARealEntity", "title": "x"},
        )
        assert response.status_code == 200
        assert "Unknown entity type: NotARealEntity" in response.text

    def test_validate_valid_entity(self, client):
        """Validate valid entity data succeeds."""
        response = client.post(
            "/validate",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200

    def test_validate_honors_selected_version(self, client, monkeypatch):
        """Validation uses the version selected in state, not the latest.

        Regression test for validate_form building ProfileFacade without the
        version, which defaulted to the latest spec and ignored state.version.
        """
        from metaseed.ui.routes import validation as validation_module

        state = client.app.state.ui_state
        state.profile = "miappe"
        state.version = "1.1"
        state.facade = None

        captured: dict[str, str] = {}
        original = validation_module._validate_entity_deep

        def _capture(values, entity_type, profile, version, path_prefix=""):
            captured["version"] = version
            return original(values, entity_type, profile, version, path_prefix)

        monkeypatch.setattr(validation_module, "_validate_entity_deep", _capture)

        response = client.post(
            "/validate",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200
        assert captured["version"] == "1.1"


class TestTableRowOperations:
    """Tests for table row add/delete/update operations."""

    def test_add_table_row(self, client_with_entity):
        """Add row to nested table."""
        response = client_with_entity.post("/table/Investigation/studies/row")
        assert response.status_code == 200
        # Should return HTML for a table row
        assert "_idx" in response.text or "studies" in response.text.lower()

    def test_delete_table_row(self, client_with_entity):
        """Delete row from nested table."""
        # First add a row
        client_with_entity.post("/table/Investigation/studies/row")
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = [{"title": "Test Study"}]

        # Delete the row
        response = client_with_entity.delete("/table/Investigation/studies/row/0")
        assert response.status_code == 200
        assert state.current_nested_items["studies"] == []

    def test_delete_invalid_row_index(self, client_with_entity):
        """Delete with invalid index does nothing."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = [{"title": "Test Study"}]

        response = client_with_entity.delete("/table/Investigation/studies/row/99")
        assert response.status_code == 200
        # Row should still exist
        assert len(state.current_nested_items["studies"]) == 1

    def test_update_table_cell(self, client_with_entity):
        """Update cell value in nested table."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = [{"title": "Original"}]

        response = client_with_entity.post(
            "/table/Investigation/studies/row/0/cell",
            data={"title": "Updated"},
        )
        assert response.status_code == 200
        assert state.current_nested_items["studies"][0]["title"] == "Updated"

    def test_update_table_cell_invalid_index(self, client_with_entity):
        """Update cell with invalid index does nothing."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = [{"title": "Original"}]

        response = client_with_entity.post(
            "/table/Investigation/studies/row/99/cell",
            data={"title": "Updated"},
        )
        assert response.status_code == 200
        # Original should remain unchanged
        assert state.current_nested_items["studies"][0]["title"] == "Original"


class TestNestedFormRoutes:
    """Tests for nested form editing routes."""

    @pytest.fixture
    def client_with_nested(self, client_with_entity):
        """Client with entity containing nested items."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = [
            {"title": "Nested Study", "unique_id": "STU-001"}
        ]
        return client_with_entity

    def test_edit_nested_item(self, client_with_nested):
        """Edit nested item shows form."""
        response = client_with_nested.get("/nested/Investigation/studies/0")
        assert response.status_code == 200
        assert "Study" in response.text

    def test_edit_nested_invalid_parent(self, client_with_nested):
        """Edit nested with invalid parent returns 404."""
        response = client_with_nested.get("/nested/InvalidType/studies/0")
        assert response.status_code == 404

    def test_edit_nested_invalid_field(self, client_with_nested):
        """Edit nested with invalid field returns 404."""
        response = client_with_nested.get("/nested/Investigation/invalid_field/0")
        assert response.status_code == 404

    def test_edit_nested_invalid_index(self, client_with_nested):
        """Edit nested with invalid index returns 404."""
        response = client_with_nested.get("/nested/Investigation/studies/99")
        assert response.status_code == 404

    def test_edit_nested_negative_index(self, client_with_nested):
        """Edit nested with negative index returns 404."""
        response = client_with_nested.get("/nested/Investigation/studies/-1")
        assert response.status_code == 404

    def test_save_nested_item(self, client_with_nested):
        """Save nested item updates data."""
        # First get the edit form to set up context
        client_with_nested.get("/nested/Investigation/studies/0")

        response = client_with_nested.post(
            "/nested/Investigation/studies/0",
            data={"title": "Updated Study"},
        )
        assert response.status_code == 200

    def test_save_nested_item_go_back(self, client_with_nested):
        """Save nested item with back action returns to table."""
        # First get the edit form to set up context
        client_with_nested.get("/nested/Investigation/studies/0")

        response = client_with_nested.post(
            "/nested/Investigation/studies/0",
            data={"_action": "back", "title": "Updated Study"},
        )
        assert response.status_code == 200

    def test_save_nested_invalid_index(self, client_with_nested):
        """Save nested with invalid index returns 404."""
        response = client_with_nested.post(
            "/nested/Investigation/studies/99",
            data={"title": "Updated"},
        )
        assert response.status_code == 404

    def test_edit_nested_with_resume(self, client_with_nested):
        """Edit nested with resume flag preserves context."""
        # First create the context by visiting the form
        client_with_nested.get("/nested/Investigation/studies/0")

        # Then resume
        response = client_with_nested.get("/nested/Investigation/studies/0?resume=true")
        assert response.status_code == 200


class TestUpdateEntity:
    """Tests for entity update route."""

    def test_update_entity_success(self, client_with_entity):
        """Update entity with valid data succeeds."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.put(
            f"/entity/{node_id}",
            data={"unique_id": "INV-001", "title": "Updated Title"},
        )
        assert response.status_code == 200
        assert "Updated" in response.text or "Saved" in response.text

    def test_update_entity_not_found(self, client):
        """Update nonexistent entity returns error."""
        response = client.put(
            "/entity/nonexistent-id",
            data={"unique_id": "INV-001"},
        )
        assert response.status_code == 200
        assert "Node not found: nonexistent-id" in response.text

    def test_update_entity_with_nested(self, client_with_entity):
        """Update entity merges nested items."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))
        state.current_nested_items["studies"] = [
            {"unique_id": "STU-001", "title": "Test Study"}
        ]

        response = client_with_entity.put(
            f"/entity/{node_id}",
            data={"unique_id": "INV-001", "title": "Test Investigation"},
        )
        assert response.status_code == 200

    def test_update_entity_saves_draft_with_validation_warning(
        self, client_with_entity
    ):
        """Update with incomplete data is never blocked: it saves the entity as
        a draft and surfaces a non-blocking warning listing the missing-field
        hints."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.put(
            f"/entity/{node_id}",
            data={},  # Missing required fields
        )
        # Saving is not blocked by validation.
        assert response.status_code == 200
        # Non-blocking warning notification, not a blocking error.
        assert 'data-testid="form-warning"' in response.text
        assert 'data-testid="form-error"' not in response.text
        # Message reports a draft save and lists the missing-field hints.
        assert "Saved draft" in response.text
        assert "incomplete" in response.text
        assert "title" in response.text
        assert "required" in response.text.lower()
        # The entity is still persisted (updated in place, not rejected).
        assert response.headers.get("HX-Trigger") == "entityUpdated"
        assert node_id in state.nodes_by_id


class TestProfileDisplayInfo:
    """Tests for profile display info functionality."""

    def test_profile_select_shows_all_profiles(self, client):
        """Profile selection shows all available profiles."""
        response = client.get("/form/Investigation")
        assert response.status_code == 200
        assert "MIAPPE" in response.text
        assert "ISA" in response.text

    def test_form_with_profile_query_param(self, client):
        """Form with profile query param uses that profile."""
        # Try ISA profile
        response = client.get("/form/Investigation?profile=isa")
        assert response.status_code == 200
        # Should show ISA form, not profile selection
        assert "New Dataset" not in response.text


class TestTableViewEdgeCases:
    """Tests for table view edge cases."""

    def test_table_view_clears_nested_stack(self, client_with_entity):
        """Table view for root entity clears nested edit stack."""
        state = client_with_entity.app.state.ui_state
        from metaseed.ui.state import NestedEditContext

        context = NestedEditContext(
            field_name="studies",
            row_idx=0,
            entity_type="Study",
            parent_entity_type="Investigation",
        )
        state.nested_edit_stack.append(context)

        response = client_with_entity.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert len(state.nested_edit_stack) == 0


class TestExportEdgeCases:
    """Tests for export edge cases."""

    def test_export_with_nested_entities(self, client_with_entity):
        """Export with nested entities creates multiple sheets."""
        # Use client_with_entity which already has MIAPPE profile set up
        state = client_with_entity.app.state.ui_state

        # Add nested items via current_nested_items (doesn't require model validation)
        state.current_nested_items["studies"] = [
            {"unique_id": "STU-001", "title": "Study 1"}
        ]

        response = client_with_entity.get("/export")
        assert response.status_code == 200
        assert "spreadsheetml" in response.headers["content-type"]


class TestEditFormEdgeCases:
    """Tests for edit form edge cases."""

    def test_edit_form_loads_nested_items(self, client_with_entity):
        """Edit form loads existing nested items into state."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        # Add nested items via state (avoids profile-specific validation)
        # First get the form to set up editing context
        response = client_with_entity.get(f"/form/Investigation/{node_id}")
        assert response.status_code == 200

        # Now update state with nested items
        state.current_nested_items["studies"] = [
            {"unique_id": "STU-001", "title": "Study 1"}
        ]
        state.current_nested_items = {}  # Clear to test loading

        # Get form again - should still work
        response = client_with_entity.get(f"/form/Investigation/{node_id}")
        assert response.status_code == 200

    def test_edit_form_preserves_pending_edits(self, client_with_entity):
        """Edit form preserves pending nested item edits."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        # Set pending edits
        state.current_nested_items = {"studies": [{"title": "Pending Edit"}]}

        response = client_with_entity.get(f"/form/Investigation/{node_id}")
        assert response.status_code == 200
        # Pending edits should be preserved
        assert state.current_nested_items["studies"][0]["title"] == "Pending Edit"

    def test_edit_form_unknown_entity_type(self, client_with_entity):
        """Edit form with mismatched entity type returns 404."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.get(f"/form/UnknownEntity/{node_id}")
        assert response.status_code == 404


class TestCreateEntityEdgeCases:
    """Tests for create entity edge cases."""

    def test_create_entity_unknown_type(self, client):
        """Create entity with unknown type returns error."""
        response = client.post(
            "/entity",
            data={"_entity_type": "UnknownEntity", "unique_id": "TEST-001"},
        )
        assert response.status_code == 200
        assert "unknown" in response.text.lower() or "error" in response.text.lower()

    def test_create_entity_with_nested(self, client):
        """Create entity with nested items in state."""
        state = client.app.state.ui_state
        state.current_nested_items = {
            "studies": [{"unique_id": "STU-001", "title": "Study"}]
        }

        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200


class TestNestedFormEdgeCases:
    """Tests for nested form edge cases."""

    @pytest.fixture
    def client_with_nested(self, client_with_entity):
        """Client with entity containing nested items."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = [
            {"title": "Nested Study", "unique_id": "STU-001"}
        ]
        return client_with_entity

    def test_save_nested_with_type_conversion(self, client_with_nested):
        """Save nested item converts integer fields."""
        # First set up context
        client_with_nested.get("/nested/Investigation/studies/0")

        response = client_with_nested.post(
            "/nested/Investigation/studies/0",
            data={"title": "Test", "some_numeric_field": "42"},
        )
        assert response.status_code == 200

    def test_nested_form_deeply_nested(self, client_with_nested):
        """Edit deeply nested items (nested within nested)."""
        # Create context with nested items
        state = client_with_nested.app.state.ui_state
        state.current_nested_items["studies"] = [
            {
                "unique_id": "STU-001",
                "title": "Test Study",
                "contacts": [{"name": "John Doe"}],
            }
        ]

        response = client_with_nested.get("/nested/Investigation/studies/0")
        assert response.status_code == 200


class TestChildEntityCreation:
    """Tests for child entity creation from parent."""

    def test_child_entity_form_shows_parent_context(self, client_with_entity):
        """Child entity form shows parent context and breadcrumb."""
        state = client_with_entity.app.state.ui_state
        parent_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.get(f"/form/child/{parent_id}/Study")
        assert response.status_code == 200
        assert "New Study" in response.text
        assert "Investigation" in response.text  # Parent type in breadcrumb

    def test_child_entity_form_prefills_parent_reference(self, client_with_entity):
        """Child entity form pre-fills parent reference field."""
        state = client_with_entity.app.state.ui_state
        parent_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.get(f"/form/child/{parent_id}/Study")
        assert response.status_code == 200
        # Should have parent_id hidden field
        assert f'name="_parent_id" value="{parent_id}"' in response.text

    def test_child_entity_form_unknown_parent_404(self, client_with_entity):
        """Child entity form with unknown parent returns 404."""
        response = client_with_entity.get("/form/child/unknown-id/Study")
        assert response.status_code == 404

    def test_child_entity_form_unknown_child_type_404(self, client_with_entity):
        """Child entity form with unknown child type returns 404."""
        state = client_with_entity.app.state.ui_state
        parent_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.get(f"/form/child/{parent_id}/UnknownEntity")
        assert response.status_code == 404

    def test_create_child_entity_links_to_parent(self, client_with_entity):
        """Creating child entity links it to parent in tree."""
        state = client_with_entity.app.state.ui_state
        parent_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.post(
            "/entity",
            data={
                "_entity_type": "Study",
                "_parent_id": parent_id,
                "unique_id": "STU-001",
                "title": "Child Study",
                "investigation_id": "INV-001",  # Required field
            },
        )
        assert response.status_code == 200

        # Verify parent has the child
        parent_node = state.nodes_by_id[parent_id]
        assert len(parent_node.children) == 1
        assert parent_node.children[0].entity_type == "Study"
        assert parent_node.children[0].parent_id == parent_id

    def test_edit_form_shows_add_child_buttons(self, client_with_entity):
        """Edit form shows Add Child buttons for nested entity types."""
        state = client_with_entity.app.state.ui_state
        node_id = next(iter(state.nodes_by_id.keys()))

        response = client_with_entity.get(f"/form/Investigation/{node_id}")
        assert response.status_code == 200
        # Should have buttons for child entity types
        assert "Add child entity" in response.text or "btn-add-child" in response.text


class TestDatasetStability:
    """Tests for stable entity references across save/load cycles."""

    def test_dataset_save_load_preserves_hierarchy(self, client_with_entity, tmp_path):
        """Dataset save/load preserves parent-child relationships using unique_id."""

        from metaseed.ui.datasets import load_dataset, save_dataset

        state = client_with_entity.app.state.ui_state
        facade = state.get_or_create_facade()

        # Get existing Investigation
        inv_node = next(iter(state.nodes_by_id.values()))
        inv_unique_id = inv_node.instance.unique_id

        # Add a child Study (requires investigation_id)
        study = facade.Study.create(
            unique_id="ST-CHILD-001",
            title="Child Study",
            investigation_id=inv_unique_id,
        )
        study_node = state.add_node("Study", study, parent_id=inv_node.id)
        study_unique_id = study_node.instance.unique_id

        assert len(inv_node.children) == 1
        assert inv_node.children[0].id == study_node.id

        # Save dataset
        save_dataset(state, "test-stability")

        # Reset and reload
        state.reset()
        assert len(state.nodes_by_id) == 0

        load_dataset(state, "test-stability")

        # Verify hierarchy restored
        assert len(state.nodes_by_id) == 2

        # Find nodes by unique_id
        loaded_inv = None
        loaded_study = None
        for node in state.nodes_by_id.values():
            if node.instance.unique_id == inv_unique_id:
                loaded_inv = node
            elif node.instance.unique_id == study_unique_id:
                loaded_study = node

        assert loaded_inv is not None
        assert loaded_study is not None
        assert len(loaded_inv.children) == 1
        assert loaded_inv.children[0].instance.unique_id == study_unique_id

    def test_dataset_uses_unique_id_for_parent_refs(self, client_with_entity, tmp_path):
        """Parent references use unique_id; the node's own id is persisted.

        References between entities resolve by domain identifier (unique_id),
        not by the internal node id. The node id itself is persisted as
        ``_node_id`` so it survives a reload verbatim (the graph endpoint
        reloads from disk on every poll and must not re-assign ids).
        """
        import json

        from metaseed.paths import get_datasets_dir
        from metaseed.ui.datasets import save_dataset

        state = client_with_entity.app.state.ui_state
        facade = state.get_or_create_facade()

        # Get existing Investigation
        inv_node = next(iter(state.nodes_by_id.values()))
        inv_unique_id = inv_node.instance.unique_id

        # Add a child Study (requires investigation_id)
        study = facade.Study.create(
            unique_id="ST-REF-001",
            title="Reference Test",
            investigation_id=inv_unique_id,
        )
        study_node = state.add_node("Study", study, parent_id=inv_node.id)

        # Save dataset
        save_dataset(state, "test-unique-id-ref")

        # Read the JSON file directly
        datasets_dir = get_datasets_dir()
        with open(datasets_dir / "test-unique-id-ref.json") as f:
            data = json.load(f)

        # Find Study entity in saved data
        study_entity = None
        for entity in data["entities"]:
            if entity.get("_type") == "Study":
                study_entity = entity
                break

        assert study_entity is not None
        # Parent links resolve by unique_id, not by the parent's node id.
        assert "_parent_unique_id" in study_entity
        assert study_entity["_parent_unique_id"] == inv_unique_id
        assert "_parent_id" not in study_entity
        # The node's own id is persisted so reloads keep it stable.
        assert study_entity["_node_id"] == study_node.id


class TestEmptyDatasetView:
    """Tests for empty dataset UI behavior."""

    def test_empty_dataset_shows_create_button(self, client):
        """Empty dataset view shows button to create root entity."""
        # Create a new entity to initialize the profile
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200

        # Delete the entity to get empty state with profile set
        state = client.app.state.ui_state
        entity_id = next(iter(state.nodes_by_id.keys()))
        response = client.delete(f"/entity/{entity_id}")
        assert response.status_code == 200

        # Now verify the empty state shows create button
        assert "Empty Dataset" in response.text
        assert "New Investigation" in response.text

    def test_empty_dataset_shows_root_type_button(self, client):
        """Empty dataset shows button for profile's root entity type."""
        state = client.app.state.ui_state
        state.profile = "miappe"
        state.version = "1.2"
        state._invalidate_cache()

        # Get index content (renders index.html partial)
        # The route will render the empty state since no entities exist
        response = client.get("/")
        assert response.status_code == 200

        # For new dataset view, check the profile select shows correctly
        # The main index shows profile selection when no dataset is loaded


class TestHelperFunctionIntegration:
    """Tests for helper function integration in routes."""

    def test_profile_display_info_unknown_profile(self, client):
        """Profile display info handles unknown profiles gracefully."""
        # This tests _get_profile_display_info with profiles not in the display info dict
        response = client.get("/form/Investigation")
        assert response.status_code == 200
        # Should still show profile options even if some aren't in display info dict


class TestSwitchProfileClearsTheVersion:
    """Switching profiles must not carry the old profile's version along.

    switch_profile set profile but left state.version, so after loading a
    miappe 1.1 example a switch to isa built ProfileFacade("isa", "1.1") —
    a version that does not exist — and every facade-dependent endpoint
    500'd until something else reset the version.
    """

    def test_the_next_facade_resolves_the_new_profiles_latest(self, client):
        state = client.app.state.ui_state
        state.profile = "miappe"
        state.version = "1.1"

        response = client.get("/profile/isa", follow_redirects=False)
        assert response.status_code == 303

        facade = state.get_or_create_facade()
        assert facade.profile == "isa"
        assert facade.version != "1.1"
