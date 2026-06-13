"""Tests for navigation helper functions."""

from metaseed.ui.helpers.navigation_helpers import get_parent_identifier
from metaseed.ui.state import AppState, NestedEditContext


class TestGetParentIdentifier:
    """Tests for get_parent_identifier."""

    def test_returns_identifier_from_editing_node(self):
        """When the editing node matches the parent type, return its field value."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)
        state.editing_node_id = run_node.id

        result = get_parent_identifier(state, "Run", "alias")

        assert result == "run1"

    def test_returns_empty_string_when_parent_only_in_nested_stack(self):
        """A parent present only in the nested edit stack yields an empty string.

        The nested-stack branch carries no identifier resolution, so the helper
        falls through to the empty-string fallback rather than guessing.
        """
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        state.nested_edit_stack = [
            NestedEditContext(
                parent_entity_type="Run",
                entity_type="Run",
                field_name="files",
                row_idx=0,
            )
        ]

        result = get_parent_identifier(state, "Run", "alias")

        assert result == ""

    def test_returns_empty_string_when_no_match(self):
        """No editing node and no matching context returns an empty string."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"

        assert get_parent_identifier(state, "Run", "alias") == ""
