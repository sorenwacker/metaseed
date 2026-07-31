"""Tests for the spec-builder MCP tools.

Drive the registered tools end to end against a session draft, mirroring how an
MCP client would. The authoring logic itself is unit-tested in
tests/test_specs/test_builder.py; these tests pin the tool layer: draft session
handling, name-based addressing, JSON contract, and error reporting.
"""

from __future__ import annotations

import json

import pytest

from metaseed.agent.mcp.server import create_server, reset_mcp_state
from tests.test_agent.helpers import get_tool


@pytest.fixture
def server():
    """Fresh MCP server with a clean session draft per test."""
    reset_mcp_state()
    srv = create_server("test-spec-builder")
    yield srv
    reset_mcp_state()


def call(server, tool, **kwargs):
    """Invoke a registered tool and parse its JSON result."""
    fn = get_tool(server, tool)
    assert fn is not None, f"tool {tool} not registered"
    return json.loads(fn(**kwargs))


class TestDraftLifecycle:
    def test_edit_before_draft_errors(self, server):
        result = call(server, "spec_add_entity", name="Study")
        assert "error" in result

    def test_create_starts_draft(self, server):
        result = call(server, "spec_create", name="p", version="0.1")
        assert result["name"] == "p"
        assert result["version"] == "0.1"
        assert result["entities"] == {}

    def test_status_reflects_edits(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        status = call(server, "spec_status")
        assert "Study" in status["entities"]

    def test_clone_unknown_profile_errors(self, server):
        result = call(server, "spec_clone", profile="nope", version="9.9")
        assert "error" in result

    def test_import_yaml_round_trips(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        yaml_text = get_tool(server, "spec_preview_yaml")()

        call(server, "spec_import_yaml", yaml_text=yaml_text)
        status = call(server, "spec_status")
        assert "Study" in status["entities"]

    def test_import_invalid_yaml_errors(self, server):
        result = call(server, "spec_import_yaml", yaml_text="name: [bad")
        assert "error" in result


class TestEntitiesAndFields:
    def test_add_nested_field_creates_back_reference(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Investigation")
        call(server, "spec_add_entity", name="Study")

        status = call(
            server,
            "spec_add_field",
            entity="Investigation",
            name="studies",
            field_type="list",
            items="Study",
        )

        assert "identifier" in status["entities"]["Investigation"]
        # Study gains a back-reference field
        assert any(f.endswith("_id") for f in status["entities"]["Study"])

    def test_rename_entity_cascades(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Investigation")
        call(server, "spec_add_entity", name="Study")
        call(
            server,
            "spec_add_field",
            entity="Investigation",
            name="studies",
            field_type="list",
            items="Study",
        )

        call(server, "spec_rename_entity", old_name="Study", new_name="Trial")
        yaml_text = get_tool(server, "spec_preview_yaml")()
        assert "items: Trial" in yaml_text
        assert "items: Study" not in yaml_text

    def test_update_and_delete_field_by_name(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        call(
            server, "spec_add_field", entity="Study", name="title", field_type="string"
        )

        call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="title",
            required=True,
        )
        call(server, "spec_delete_field", entity="Study", field_name="title")
        status = call(server, "spec_status")
        assert status["entities"]["Study"] == []

    def test_move_field(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        call(server, "spec_add_field", entity="Study", name="a", field_type="string")
        call(server, "spec_add_field", entity="Study", name="b", field_type="string")

        status = call(
            server, "spec_move_field", entity="Study", field_name="b", direction="up"
        )
        assert status["entities"]["Study"] == ["b", "a"]

    def test_duplicate_entity_errors(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        result = call(server, "spec_add_entity", name="Study")
        assert "error" in result


class TestRulesAndValidation:
    def test_rule_lifecycle(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_rule", name="r1", message="hold")
        call(server, "spec_update_rule", rule_name="r1", message="changed")
        status = call(server, "spec_status")
        assert "r1" in status["validation_rules"]

        call(server, "spec_delete_rule", rule_name="r1")
        status = call(server, "spec_status")
        assert status["validation_rules"] == []

    def test_set_root_entity_requires_existing(self, server):
        call(server, "spec_create", name="p", version="0.1")
        result = call(server, "spec_set_root_entity", entity="Ghost")
        assert "error" in result

    def test_validate_reports_dangling_reference(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Investigation")
        call(
            server,
            "spec_add_field",
            entity="Investigation",
            name="studies",
            field_type="list",
            items="Ghost",
        )
        result = call(server, "spec_validate")
        assert result["valid"] is False
        assert any("Ghost" in issue for issue in result["issues"])

    def test_validate_clean_after_real_clone(self, server):
        call(server, "spec_clone", profile="miappe", version="1.2")
        result = call(server, "spec_validate")
        assert result["valid"] is True
        assert result["issues"] == []


class TestSpecCompare:
    """`spec_compare` reports what the draft's edits imply for the version.

    Classification itself is unit-tested in tests/test_specs/test_compare.py;
    these pin the tool layer.
    """

    def test_compare_before_a_draft_errors(self, server):
        result = call(server, "spec_compare", profile="miappe", version="1.2")
        assert "error" in result

    def test_compare_against_an_unknown_release_errors(self, server):
        call(server, "spec_create", name="p", version="1.0")
        result = call(server, "spec_compare", profile="nope", version="9.9")
        assert "error" in result

    def test_an_untouched_clone_needs_no_bump(self, server):
        call(server, "spec_clone", profile="miappe", version="1.2")

        result = call(server, "spec_compare", profile="miappe", version="1.2")

        assert result["required_bump"] == "none"
        assert result["breaking"] == []
        assert result["compatible"] == []
        assert result["old"]["content_hash"] == result["new"]["content_hash"]

    def test_a_new_required_field_demands_a_major_bump(self, server):
        call(server, "spec_clone", profile="miappe", version="1.2")
        call(
            server,
            "spec_add_field",
            entity="Investigation",
            name="funding_statement",
            field_type="string",
            required=True,
        )

        result = call(server, "spec_compare", profile="miappe", version="1.2")

        assert result["required_bump"] == "major"
        assert result["declared_bump"] == "none"
        assert result["bump_satisfied"] is False
        assert [c["target"] for c in result["breaking"]] == [
            "Investigation.funding_statement"
        ]
        assert result["breaking"][0]["message"]

    def test_declaring_the_required_bump_satisfies_the_check(self, server):
        call(server, "spec_clone", profile="miappe", version="1.2")
        call(
            server,
            "spec_add_field",
            entity="Investigation",
            name="funding_statement",
            field_type="string",
            required=True,
        )
        call(server, "spec_set_metadata", version="2.0")

        result = call(server, "spec_compare", profile="miappe", version="1.2")

        assert result["required_bump"] == "major"
        assert result["declared_bump"] == "major"
        assert result["bump_satisfied"] is True

    def test_an_optional_field_only_needs_a_minor_bump(self, server):
        call(server, "spec_clone", profile="miappe", version="1.2")
        call(
            server,
            "spec_add_field",
            entity="Investigation",
            name="funding_statement",
            field_type="string",
        )
        call(server, "spec_set_metadata", version="1.3")

        result = call(server, "spec_compare", profile="miappe", version="1.2")

        assert result["required_bump"] == "minor"
        assert result["bump_satisfied"] is True
        assert result["breaking"] == []

    def test_a_malformed_draft_version_is_reported(self, server):
        call(server, "spec_clone", profile="miappe", version="1.2")
        call(server, "spec_set_metadata", version="1.3-dev")

        result = call(server, "spec_compare", profile="miappe", version="1.2")

        assert "MAJOR.MINOR" in result["error"]
