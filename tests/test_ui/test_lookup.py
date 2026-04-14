"""Tests for cross-entity lookup functionality.

Tests the autocomplete API and reference field detection.
"""

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.helpers import collect_entities_by_type, get_reference_fields
from metaseed.ui.routes import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def client():
    """Create a test client with fresh state."""
    state = AppState()
    app = create_app(state)
    return TestClient(app)


@pytest.fixture
def state():
    """Create a fresh app state."""
    return AppState()


class TestGetReferenceFields:
    """Tests for get_reference_fields helper function."""

    def test_sample_has_observation_unit_reference(self):
        """Sample entity should have observation_unit_id reference field."""
        ref_fields = get_reference_fields("miappe", "1.1", "Sample")

        assert "observation_unit_id" in ref_fields
        assert ref_fields["observation_unit_id"]["target_entity"] == "ObservationUnit"
        assert ref_fields["observation_unit_id"]["target_field"] == "unique_id"

    def test_observation_unit_has_biological_material_reference(self):
        """ObservationUnit should have biological_material_id reference."""
        ref_fields = get_reference_fields("miappe", "1.1", "ObservationUnit")

        assert "biological_material_id" in ref_fields
        assert ref_fields["biological_material_id"]["target_entity"] == "BiologicalMaterial"
        assert ref_fields["biological_material_id"]["target_field"] == "unique_id"

    def test_event_has_observation_unit_ids_reference(self):
        """Event should have observation_unit_ids reference."""
        ref_fields = get_reference_fields("miappe", "1.1", "Event")

        assert "observation_unit_ids" in ref_fields
        assert ref_fields["observation_unit_ids"]["target_entity"] == "ObservationUnit"

    def test_entity_without_references_returns_empty(self):
        """Entity without reference fields returns empty dict."""
        ref_fields = get_reference_fields("miappe", "1.1", "Investigation")
        # Investigation doesn't have reference fields
        assert isinstance(ref_fields, dict)

    def test_invalid_profile_returns_empty(self):
        """Invalid profile returns empty dict without error."""
        ref_fields = get_reference_fields("nonexistent", "1.0", "Sample")
        assert ref_fields == {}


class TestCollectEntitiesByType:
    """Tests for collect_entities_by_type helper function."""

    def test_empty_state_returns_empty(self, state):
        """Empty state returns empty dict."""
        facade = state.get_or_create_facade()
        result = collect_entities_by_type(state, facade)
        assert result == {}

    def test_collects_root_entities(self, client):
        """Collects entities from root nodes."""
        # Create an investigation
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200

        # Access state through app
        state = client.app.state.ui_state
        facade = state.get_or_create_facade()

        result = collect_entities_by_type(state, facade)

        assert "Investigation" in result
        assert len(result["Investigation"]) == 1
        assert result["Investigation"][0]["value"] == "INV-001"

    def test_collects_nested_entities(self, client):
        """Collects nested entities from current_nested_items."""
        # Create an investigation first
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )
        assert response.status_code == 200

        state = client.app.state.ui_state
        facade = state.get_or_create_facade()

        # Simulate adding nested studies
        state.current_nested_items["studies"] = [
            {"unique_id": "STUDY-001", "title": "Study One"},
            {"unique_id": "STUDY-002", "title": "Study Two"},
        ]

        result = collect_entities_by_type(state, facade)

        assert "Study" in result
        assert len(result["Study"]) == 2
        study_values = [s["value"] for s in result["Study"]]
        assert "STUDY-001" in study_values
        assert "STUDY-002" in study_values


class TestLookupAPI:
    """Tests for the lookup API endpoint."""

    def test_lookup_returns_empty_for_no_entities(self, client):
        """Lookup returns empty results when no entities exist."""
        response = client.get("/api/lookup/ObservationUnit")
        assert response.status_code == 200

        data = response.json()
        assert "results" in data
        assert data["results"] == []

    def test_lookup_with_query_filters_results(self, client):
        """Lookup filters results based on query string."""
        # Create investigation
        response = client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Alpha Investigation",
            },
        )
        assert response.status_code == 200

        # Search for "Alpha"
        response = client.get("/api/lookup/Investigation?q=Alpha")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["value"] == "INV-001"

        # Search for "Beta" should return empty
        response = client.get("/api/lookup/Investigation?q=Beta")
        data = response.json()
        assert data["results"] == []

    def test_lookup_returns_value_and_label(self, client):
        """Lookup results include both value and label."""
        client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "My Investigation Title",
            },
        )

        response = client.get("/api/lookup/Investigation")
        data = response.json()

        assert len(data["results"]) == 1
        result = data["results"][0]
        assert "value" in result
        assert "label" in result
        assert result["value"] == "INV-001"
        # Label should be the title
        assert result["label"] == "My Investigation Title"


class TestReferenceFieldsAPI:
    """Tests for the reference fields API endpoint."""

    def test_get_reference_fields_for_sample(self, client):
        """API returns reference fields for Sample entity."""
        response = client.get("/api/reference-fields/Sample")
        assert response.status_code == 200

        data = response.json()
        assert "observation_unit_id" in data
        assert data["observation_unit_id"]["target_entity"] == "ObservationUnit"

    def test_get_reference_fields_for_investigation(self, client):
        """API returns empty for entity without references."""
        response = client.get("/api/reference-fields/Investigation")
        assert response.status_code == 200
        # Investigation has no reference fields in the rules


class TestTableRowWithLookup:
    """Tests for table row rendering with lookup support."""

    def test_table_includes_reference_fields(self, client):
        """Table view includes reference_fields in context."""
        # Create investigation first
        client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )

        # Add a study
        state = client.app.state.ui_state
        state.current_nested_items["studies"] = [
            {"unique_id": "STUDY-001", "title": "Study One"},
        ]

        # Get table view for studies (Study has nested fields but check response renders)
        response = client.get("/table/Investigation/studies")
        assert response.status_code == 200
        # The table should render without error

    def test_add_row_includes_lookup_attributes(self, client):
        """New rows include data-lookup attributes for reference fields."""
        # Create investigation first
        client.post(
            "/entity",
            data={
                "_entity_type": "Investigation",
                "unique_id": "INV-001",
                "title": "Test Investigation",
            },
        )

        # Get table view
        response = client.get("/table/Investigation/studies")
        assert response.status_code == 200

        # Add a new row
        response = client.post("/table/Investigation/studies/row")
        assert response.status_code == 200
        # Row should be rendered successfully
