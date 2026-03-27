"""Tests for the HTMX UI routes.

Tests use FastAPI TestClient to verify route behavior.
"""

import pytest
from fastapi.testclient import TestClient

from miappe_api.ui.routes import AppState, create_app


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
        """Index page contains MIAPPE-API title."""
        response = client.get("/")
        assert "MIAPPE-API" in response.text

    def test_index_contains_profile_select(self, client):
        """Index page contains profile selector."""
        response = client.get("/")
        assert "profile-select" in response.text
        assert "miappe" in response.text

    def test_index_contains_entity_buttons(self, client):
        """Index page contains entity creation buttons."""
        response = client.get("/")
        assert "Investigation" in response.text


class TestSidebar:
    """Tests for the sidebar partial."""

    def test_sidebar_returns_partial(self, client):
        """Sidebar route returns partial HTML."""
        response = client.get("/sidebar")
        assert response.status_code == 200
        assert "Project" in response.text

    def test_sidebar_empty_initially(self, client):
        """Sidebar shows empty message when no entities."""
        response = client.get("/sidebar")
        assert "No entities created yet" in response.text

    def test_sidebar_shows_entity_after_create(self, client_with_entity):
        """Sidebar shows entity after creation."""
        response = client_with_entity.get("/sidebar")
        assert "Test Investigation" in response.text


class TestForm:
    """Tests for entity forms."""

    def test_new_form_returns_html(self, client):
        """New entity form route returns HTML."""
        response = client.get("/form/Investigation")
        assert response.status_code == 200
        assert "New Investigation" in response.text

    def test_new_form_contains_required_fields(self, client):
        """Form contains required fields section."""
        response = client.get("/form/Investigation")
        assert "Required Fields" in response.text
        assert "unique_id" in response.text
        assert "title" in response.text

    def test_new_form_contains_optional_fields(self, client):
        """Form contains optional fields section."""
        response = client.get("/form/Investigation")
        assert "Optional Fields" in response.text

    def test_new_form_unknown_entity_404(self, client):
        """Unknown entity type returns 404."""
        response = client.get("/form/UnknownEntity")
        assert response.status_code == 404


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

    def test_create_entity_validation_error(self, client):
        """Create with invalid data shows validation error."""
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
            },
        )
        assert response.status_code == 200
        assert "error" in response.text.lower() or "required" in response.text.lower()


class TestEditEntity:
    """Tests for entity editing."""

    def test_edit_form_shows_values(self, client_with_entity):
        """Edit form shows existing values."""
        sidebar = client_with_entity.get("/sidebar")
        assert "Test Investigation" in sidebar.text

        response = client_with_entity.get("/form/Investigation")
        assert response.status_code == 200

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

        sidebar = client.get("/sidebar")
        assert "To Delete" in sidebar.text

        state = client.app.state.ui_state
        node_id = list(state.nodes_by_id.keys())[0]

        delete_response = client.delete(f"/entity/{node_id}")
        assert delete_response.status_code == 200

        sidebar_after = client.get("/sidebar")
        assert "To Delete" not in sidebar_after.text

    def test_delete_unknown_node_error(self, client):
        """Delete nonexistent node returns error."""
        response = client.delete("/entity/nonexistent")
        assert response.status_code == 200
        assert "error" in response.text.lower() or "not found" in response.text.lower()


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

    def test_switch_to_combined(self, client):
        """Switch to combined profile redirects."""
        response = client.get("/profile/combined", follow_redirects=False)
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
        response = client.get("/static/js/app.js")
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
        instance = facade.Investigation(unique_id="INV-001", title="Test")
        node = state.add_node("Investigation", instance)

        assert node.id in state.nodes_by_id
        assert len(state.entity_tree) == 1
        assert node.label == "Test"

    def test_update_node(self):
        """Update existing node."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Original")
        node = state.add_node("Investigation", instance)

        updated_instance = facade.Investigation(unique_id="INV-001", title="Updated")
        state.update_node(node.id, updated_instance)

        assert state.nodes_by_id[node.id].label == "Updated"

    def test_delete_node(self):
        """Delete node from tree."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Test")
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
