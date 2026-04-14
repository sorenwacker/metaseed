"""Tests for Excel-style bulk editing features.

Tests cover bulk update endpoint, paste endpoint, and selection UI elements.
"""

import json

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.routes import AppState, create_app


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


@pytest.fixture
def client_with_studies(client_with_entity):
    """Client with entity containing multiple studies for bulk operations."""
    state = client_with_entity.app.state.ui_state
    state.current_nested_items["studies"] = [
        {"unique_id": "STU-001", "title": "Study One"},
        {"unique_id": "STU-002", "title": "Study Two"},
        {"unique_id": "STU-003", "title": "Study Three"},
    ]
    return client_with_entity


class TestBulkUpdateEndpoint:
    """Tests for POST /table/{parent}/{field}/bulk endpoint."""

    def test_bulk_update_single_row(self, client_with_studies):
        """Bulk update works for a single row."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Updated Title",
                "indices": "0",
            },
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "Updated Title"
        assert state.current_nested_items["studies"][1]["title"] == "Study Two"

    def test_bulk_update_multiple_rows(self, client_with_studies):
        """Bulk update works for multiple rows."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Bulk Updated",
                "indices": "0,1,2",
            },
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert all(s["title"] == "Bulk Updated" for s in state.current_nested_items["studies"])

    def test_bulk_update_partial_indices(self, client_with_studies):
        """Bulk update works for subset of rows."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Partial Update",
                "indices": "0,2",
            },
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "Partial Update"
        assert state.current_nested_items["studies"][1]["title"] == "Study Two"
        assert state.current_nested_items["studies"][2]["title"] == "Partial Update"

    def test_bulk_update_missing_field(self, client_with_studies):
        """Bulk update with missing field returns error."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-value": "Value",
                "indices": "0",
            },
        )
        assert response.status_code == 200
        assert "required" in response.text.lower() or "error" in response.text.lower()

    def test_bulk_update_missing_indices(self, client_with_studies):
        """Bulk update with missing indices returns error."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Value",
            },
        )
        assert response.status_code == 200
        assert "required" in response.text.lower() or "error" in response.text.lower()

    def test_bulk_update_invalid_indices(self, client_with_studies):
        """Bulk update with invalid indices returns error."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Value",
                "indices": "abc,xyz",
            },
        )
        assert response.status_code == 200
        assert "invalid" in response.text.lower() or "error" in response.text.lower()

    def test_bulk_update_out_of_range_indices(self, client_with_studies):
        """Bulk update ignores out-of-range indices gracefully."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Updated",
                "indices": "0,99",
            },
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "Updated"
        assert len(state.current_nested_items["studies"]) == 3

    def test_bulk_update_returns_refreshed_table(self, client_with_studies):
        """Bulk update returns the refreshed table HTML."""
        response = client_with_studies.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "New Title",
                "indices": "0",
            },
        )
        assert response.status_code == 200
        assert "data-table" in response.text or "table" in response.text.lower()


class TestPasteEndpoint:
    """Tests for POST /table/{parent}/{field}/paste endpoint."""

    def test_paste_single_cell(self, client_with_studies):
        """Paste updates a single cell."""
        changes = [{"idx": 0, "field": "title", "value": "Pasted Title"}]
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": json.dumps(changes)},
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "Pasted Title"

    def test_paste_multiple_cells_same_row(self, client_with_studies):
        """Paste updates multiple cells in the same row."""
        changes = [
            {"idx": 0, "field": "title", "value": "New Title"},
            {"idx": 0, "field": "unique_id", "value": "NEW-001"},
        ]
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": json.dumps(changes)},
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "New Title"
        assert state.current_nested_items["studies"][0]["unique_id"] == "NEW-001"

    def test_paste_multiple_rows(self, client_with_studies):
        """Paste updates cells across multiple rows."""
        changes = [
            {"idx": 0, "field": "title", "value": "Row 0"},
            {"idx": 1, "field": "title", "value": "Row 1"},
            {"idx": 2, "field": "title", "value": "Row 2"},
        ]
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": json.dumps(changes)},
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "Row 0"
        assert state.current_nested_items["studies"][1]["title"] == "Row 1"
        assert state.current_nested_items["studies"][2]["title"] == "Row 2"

    def test_paste_invalid_json(self, client_with_studies):
        """Paste with invalid JSON returns error."""
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": "not valid json"},
        )
        assert response.status_code == 200
        assert "invalid" in response.text.lower() or "error" in response.text.lower()

    def test_paste_empty_changes(self, client_with_studies):
        """Paste with empty changes list succeeds with zero updates."""
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": "[]"},
        )
        assert response.status_code == 200
        assert "0" in response.text

    def test_paste_out_of_range_index(self, client_with_studies):
        """Paste ignores out-of-range indices."""
        changes = [{"idx": 99, "field": "title", "value": "Should Not Apply"}]
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": json.dumps(changes)},
        )
        assert response.status_code == 200

        state = client_with_studies.app.state.ui_state
        assert state.current_nested_items["studies"][0]["title"] == "Study One"

    def test_paste_returns_notification(self, client_with_studies):
        """Paste returns a notification HTML response."""
        changes = [{"idx": 0, "field": "title", "value": "Pasted"}]
        response = client_with_studies.post(
            "/table/Investigation/studies/paste",
            data={"changes": json.dumps(changes)},
        )
        assert response.status_code == 200
        assert "notification" in response.text.lower() or "pasted" in response.text.lower()


class TestTableSelectionUI:
    """Tests for table selection UI elements."""

    def test_table_has_select_all_checkbox(self, client_with_studies):
        """Table header includes select-all checkbox."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'id="select-all"' in response.text
        assert 'data-testid="select-all"' in response.text

    def test_table_rows_have_checkboxes(self, client_with_studies):
        """Table rows include selection checkboxes."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'class="row-select"' in response.text
        assert 'data-testid="row-select-0"' in response.text

    def test_table_has_bulk_edit_toolbar(self, client_with_studies):
        """Table includes bulk edit toolbar."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'id="bulk-edit-toolbar"' in response.text
        assert 'data-testid="bulk-edit-toolbar"' in response.text

    def test_table_has_bulk_edit_field_dropdown(self, client_with_studies):
        """Bulk edit toolbar includes field dropdown."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'id="bulk-edit-field"' in response.text
        assert 'data-testid="bulk-edit-field"' in response.text

    def test_table_has_bulk_edit_value_input(self, client_with_studies):
        """Bulk edit toolbar includes value input."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'id="bulk-edit-value"' in response.text
        assert 'data-testid="bulk-edit-value"' in response.text

    def test_table_has_apply_button(self, client_with_studies):
        """Bulk edit toolbar includes apply button."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'data-testid="bulk-apply"' in response.text

    def test_table_has_cancel_button(self, client_with_studies):
        """Bulk edit toolbar includes cancel button."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'data-testid="bulk-cancel"' in response.text


class TestEditableCellStructure:
    """Tests for editable cell HTML structure."""

    def test_cells_have_editable_class(self, client_with_studies):
        """Table cells have editable-cell class."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'class="editable-cell"' in response.text

    def test_cells_have_display_span(self, client_with_studies):
        """Cells include display span element."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'class="cell-display"' in response.text

    def test_cells_have_input_element(self, client_with_studies):
        """Cells include input element."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'class="form-input cell-input"' in response.text

    def test_cells_have_data_attributes(self, client_with_studies):
        """Cells have data-col and data-row attributes."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert "data-col=" in response.text
        assert "data-row=" in response.text


class TestTableDataAttributes:
    """Tests for table data attributes needed by JavaScript."""

    def test_table_has_parent_type_attribute(self, client_with_studies):
        """Table has data-parent-type attribute."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'data-parent-type="Investigation"' in response.text

    def test_table_has_field_name_attribute(self, client_with_studies):
        """Table has data-field-name attribute."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'data-field-name="studies"' in response.text

    def test_table_has_id(self, client_with_studies):
        """Table has id attribute for JavaScript targeting."""
        response = client_with_studies.get("/table/Investigation/studies")
        assert response.status_code == 200
        assert 'id="data-table"' in response.text


class TestBulkEditWithEmptyTable:
    """Tests for bulk edit operations on empty tables."""

    def test_bulk_update_empty_table(self, client_with_entity):
        """Bulk update on empty table handles gracefully."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = []

        response = client_with_entity.post(
            "/table/Investigation/studies/bulk",
            data={
                "bulk-edit-field": "title",
                "bulk-edit-value": "Value",
                "indices": "0",
            },
        )
        assert response.status_code == 200

    def test_paste_empty_table(self, client_with_entity):
        """Paste on empty table handles gracefully."""
        state = client_with_entity.app.state.ui_state
        state.current_nested_items["studies"] = []

        changes = [{"idx": 0, "field": "title", "value": "Pasted"}]
        response = client_with_entity.post(
            "/table/Investigation/studies/paste",
            data={"changes": json.dumps(changes)},
        )
        assert response.status_code == 200
