"""Tests for UI helper functions."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ValidationError

from metaseed.facade import ProfileFacade
from metaseed.ui.helpers import (
    build_breadcrumb,
    collect_form_values,
    format_table_rows,
    format_validation_errors,
    get_field_data,
    get_items_store,
    get_table_column_info,
    get_table_columns,
    is_nested_field,
)
from metaseed.ui.state import AppState, NestedEditContext


class TestIsNestedField:
    """Tests for is_nested_field function."""

    def test_entity_type_is_nested(self):
        """Entity type fields are nested."""
        field = {"type": "entity", "items": "Person"}
        assert is_nested_field(field) is True

    def test_list_of_entities_is_nested(self):
        """List of entity types are nested."""
        field = {"type": "list", "items": "Study"}
        assert is_nested_field(field) is True

    def test_list_of_strings_not_nested(self):
        """List of strings is not nested."""
        field = {"type": "list", "items": "string"}
        assert is_nested_field(field) is False

    def test_list_of_ints_not_nested(self):
        """List of ints is not nested."""
        field = {"type": "list", "items": "int"}
        assert is_nested_field(field) is False

    def test_string_type_not_nested(self):
        """String type is not nested."""
        field = {"type": "string"}
        assert is_nested_field(field) is False

    def test_list_without_items_not_nested(self):
        """List without items specified is not nested."""
        field = {"type": "list"}
        assert is_nested_field(field) is False


class TestCollectFormValues:
    """Tests for collect_form_values function."""

    @pytest.fixture
    def facade(self):
        """Create test facade."""
        return ProfileFacade("miappe")

    def test_collect_string_value(self, facade):
        """Collect string values."""
        form_data = {"unique_id": "TEST-001", "title": "Test Title"}
        values = collect_form_values(form_data, facade.Investigation)
        assert values["unique_id"] == "TEST-001"
        assert values["title"] == "Test Title"

    def test_skip_empty_values(self, facade):
        """Skip empty string values."""
        form_data = {"unique_id": "TEST-001", "title": "", "description": None}
        values = collect_form_values(form_data, facade.Investigation)
        assert "title" not in values
        assert "description" not in values

    def test_convert_integer_value(self):
        """Convert integer values."""
        # Study has latitude/longitude which could be numeric
        # Let's use a mock helper with integer field
        helper = MagicMock()
        helper.all_fields = ["count"]
        helper.field_info.return_value = {"type": "integer", "required": False}

        form_data = {"count": "42"}
        values = collect_form_values(form_data, helper)
        assert values["count"] == 42

    def test_invalid_integer_skipped(self):
        """Invalid integer values are skipped."""
        helper = MagicMock()
        helper.all_fields = ["count"]
        helper.field_info.return_value = {"type": "integer", "required": False}

        form_data = {"count": "not-a-number"}
        values = collect_form_values(form_data, helper)
        assert "count" not in values

    def test_convert_float_value(self):
        """Convert float values."""
        helper = MagicMock()
        helper.all_fields = ["latitude"]
        helper.field_info.return_value = {"type": "float", "required": False}

        form_data = {"latitude": "51.5074"}
        values = collect_form_values(form_data, helper)
        assert values["latitude"] == 51.5074

    def test_invalid_float_skipped(self):
        """Invalid float values are skipped."""
        helper = MagicMock()
        helper.all_fields = ["latitude"]
        helper.field_info.return_value = {"type": "float", "required": False}

        form_data = {"latitude": "invalid"}
        values = collect_form_values(form_data, helper)
        assert "latitude" not in values

    def test_convert_boolean_true(self):
        """Convert boolean true values."""
        helper = MagicMock()
        helper.all_fields = ["active"]
        helper.field_info.return_value = {"type": "boolean", "required": False}

        for true_value in ["true", "1", "yes", "on", "TRUE", "Yes"]:
            form_data = {"active": true_value}
            values = collect_form_values(form_data, helper)
            assert values["active"] is True

    def test_convert_boolean_false(self):
        """Convert boolean false values."""
        helper = MagicMock()
        helper.all_fields = ["active"]
        helper.field_info.return_value = {"type": "boolean", "required": False}

        form_data = {"active": "false"}
        values = collect_form_values(form_data, helper)
        assert values["active"] is False

    def test_convert_string_list(self):
        """Convert newline-separated string list."""
        helper = MagicMock()
        helper.all_fields = ["tags"]
        helper.field_info.return_value = {"type": "list", "items": "string", "required": False}

        form_data = {"tags": "tag1\ntag2\n\ntag3"}
        values = collect_form_values(form_data, helper)
        assert values["tags"] == ["tag1", "tag2", "tag3"]


class TestFormatValidationErrors:
    """Tests for format_validation_errors function."""

    def test_format_required_error(self):
        """Format required field error."""

        class TestModel(BaseModel):
            name: str

        try:
            TestModel()
        except ValidationError as e:
            result = format_validation_errors(e)
            assert "name" in result
            assert "required" in result.lower()

    def test_format_email_pattern_error(self):
        """Format email pattern error with friendly message."""
        # Simulate an email validation error
        error = MagicMock()
        error.errors.return_value = [{"loc": ("email",), "msg": "String should match pattern"}]
        result = format_validation_errors(error)
        assert "Invalid email format" in result

    def test_format_date_pattern_error(self):
        """Format date pattern error with friendly message."""
        error = MagicMock()
        error.errors.return_value = [{"loc": ("start_date",), "msg": "String should match pattern"}]
        result = format_validation_errors(error)
        assert "Invalid date format" in result

    def test_format_orcid_pattern_error(self):
        """Format ORCID pattern error with friendly message."""
        error = MagicMock()
        error.errors.return_value = [{"loc": ("orcid",), "msg": "String should match pattern"}]
        result = format_validation_errors(error)
        assert "Invalid ORCID format" in result

    def test_format_generic_pattern_error(self):
        """Format generic pattern error."""
        error = MagicMock()
        error.errors.return_value = [
            {"loc": ("some_field",), "msg": "String should match pattern xyz"}
        ]
        result = format_validation_errors(error)
        assert "Invalid format" in result


class TestGetTableColumns:
    """Tests for get_table_columns function."""

    def test_get_columns_for_entity(self):
        """Get columns for a known entity type."""
        facade = ProfileFacade("miappe")
        columns = get_table_columns(facade, "Study")
        assert "unique_id" in columns
        assert "title" in columns
        # Nested fields should be excluded
        assert "persons" not in columns

    def test_get_columns_for_unknown_entity(self):
        """Get default columns for unknown entity type."""
        facade = ProfileFacade("miappe")
        columns = get_table_columns(facade, "UnknownEntity")
        assert columns == ["value"]


class TestGetTableColumnInfo:
    """Tests for get_table_column_info function."""

    def test_get_info_for_entity(self):
        """Get column info for a known entity type."""
        facade = ProfileFacade("miappe")
        info = get_table_column_info(facade, "Study")

        assert "columns" in info
        assert "column_types" in info
        assert "column_constraints" in info
        assert "required_columns" in info
        assert "has_nested_children" in info

        assert "unique_id" in info["columns"]
        assert "unique_id" in info["required_columns"]
        assert info["has_nested_children"] is True

    def test_get_info_for_unknown_entity(self):
        """Get default info for unknown entity type."""
        facade = ProfileFacade("miappe")
        info = get_table_column_info(facade, "UnknownEntity")

        assert info["columns"] == ["value"]
        assert info["column_types"] == {"value": "string"}
        assert info["has_nested_children"] is False


class TestGetItemsStore:
    """Tests for get_items_store function."""

    def test_get_items_from_current_nested(self):
        """Get items from current_nested_items when no nested context."""
        state = AppState()
        state.current_nested_items = {"studies": [{"title": "Study 1"}]}

        items_store, items = get_items_store(state, "Investigation", "studies")

        assert items_store is state.current_nested_items
        assert items == [{"title": "Study 1"}]

    def test_get_items_creates_empty_list(self):
        """Creates empty list if field not in store."""
        state = AppState()
        state.current_nested_items = {}

        items_store, items = get_items_store(state, "Investigation", "studies")

        assert items == []
        assert "studies" in items_store

    def test_get_items_from_nested_context(self):
        """Get items from nested context when editing nested entity."""
        state = AppState()
        context = NestedEditContext(
            field_name="persons",
            row_idx=0,
            entity_type="Study",
            parent_entity_type="Investigation",
            nested_items={"contacts": [{"name": "John"}]},
        )
        state.nested_edit_stack.append(context)

        items_store, items = get_items_store(state, "Study", "contacts")

        assert items_store is context.nested_items
        assert items == [{"name": "John"}]


class TestFormatTableRows:
    """Tests for format_table_rows function."""

    def test_format_dict_items(self):
        """Format dictionary items."""
        items = [{"name": "Item 1"}, {"name": "Item 2"}]
        rows = format_table_rows(items)

        assert len(rows) == 2
        assert rows[0]["name"] == "Item 1"
        assert rows[0]["_idx"] == 0
        assert rows[1]["_idx"] == 1

    def test_format_model_items(self):
        """Format Pydantic model items."""
        facade = ProfileFacade("miappe")
        study = facade.Study(unique_id="STU-001", title="Test Study", investigation_id="INV-001")
        items = [study]

        rows = format_table_rows(items)

        assert len(rows) == 1
        assert rows[0]["unique_id"] == "STU-001"
        assert rows[0]["_idx"] == 0

    def test_format_string_items(self):
        """Format string items as value dict."""
        items = ["item1", "item2"]
        rows = format_table_rows(items)

        assert len(rows) == 2
        assert rows[0]["value"] == "item1"
        assert rows[0]["_idx"] == 0


class TestBuildBreadcrumb:
    """Tests for build_breadcrumb function."""

    def test_empty_breadcrumb(self):
        """Empty breadcrumb when not editing."""
        state = AppState()
        breadcrumb = build_breadcrumb(state)
        assert breadcrumb == []

    def test_breadcrumb_with_root_entity(self):
        """Breadcrumb includes root entity."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Test Investigation")
        node = state.add_node("Investigation", instance)
        state.editing_node_id = node.id

        breadcrumb = build_breadcrumb(state)

        assert len(breadcrumb) == 1
        assert breadcrumb[0]["label"] == "Test Investigation"
        assert breadcrumb[0]["entity_type"] == "Investigation"

    def test_breadcrumb_with_nested_context(self):
        """Breadcrumb includes nested edit context."""
        state = AppState()
        facade = state.get_or_create_facade()
        instance = facade.Investigation(unique_id="INV-001", title="Root")
        node = state.add_node("Investigation", instance)
        state.editing_node_id = node.id

        # Add nested items and context
        state.current_nested_items = {"studies": [{"title": "Nested Study"}]}
        context = NestedEditContext(
            field_name="studies",
            row_idx=0,
            entity_type="Study",
            parent_entity_type="Investigation",
        )
        state.nested_edit_stack.append(context)

        breadcrumb = build_breadcrumb(state)

        assert len(breadcrumb) == 2
        assert breadcrumb[0]["label"] == "Root"
        assert breadcrumb[1]["label"] == "Nested Study"

    def test_breadcrumb_missing_node(self):
        """Breadcrumb handles missing node gracefully."""
        state = AppState()
        state.editing_node_id = "nonexistent-id"

        breadcrumb = build_breadcrumb(state)

        # Should not include the missing node
        assert len(breadcrumb) == 0


class TestGetFieldData:
    """Tests for get_field_data function."""

    def test_get_field_data(self):
        """Get field data from helper."""
        facade = ProfileFacade("miappe")
        fields = get_field_data(facade.Investigation)

        assert len(fields) > 0
        # Check structure of field data
        field = fields[0]
        assert "name" in field
        assert "type" in field
        assert "required" in field
        assert "description" in field


class TestParentIdFields:
    """Tests for parent ID field detection."""

    def test_person_investigation_id_detected(self) -> None:
        """Person.investigation_id should be detected as parent ref field."""
        from metaseed.ui.helpers import get_parent_id_fields, get_reference_fields

        ref_fields = get_reference_fields("isa", "1.0", "Person")
        parent_fields = get_parent_id_fields(ref_fields, "Investigation")

        assert "investigation_id" in parent_fields
        assert parent_fields["investigation_id"] == "identifier"

    def test_person_study_id_detected(self) -> None:
        """Person.study_id should be detected as parent ref field."""
        from metaseed.ui.helpers import get_parent_id_fields, get_reference_fields

        ref_fields = get_reference_fields("isa", "1.0", "Person")
        parent_fields = get_parent_id_fields(ref_fields, "Study")

        assert "study_id" in parent_fields
        assert parent_fields["study_id"] == "identifier"

    def test_sample_study_id_detected(self) -> None:
        """Sample.study_id should be detected as parent ref field."""
        from metaseed.ui.helpers import get_parent_id_fields, get_reference_fields

        ref_fields = get_reference_fields("isa", "1.0", "Sample")
        parent_fields = get_parent_id_fields(ref_fields, "Study")

        assert "study_id" in parent_fields
