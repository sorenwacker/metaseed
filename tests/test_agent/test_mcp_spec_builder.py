"""Tests for the spec-builder MCP tools.

Drive the registered tools end to end against a session draft, mirroring how an
MCP client would. The authoring logic itself is unit-tested in
tests/test_specs/test_builder.py; these tests pin the tool layer: draft session
handling, name-based addressing, JSON contract, and error reporting.
"""

from __future__ import annotations

import inspect
import json

import pytest
import yaml

from metaseed.agent.mcp.server import create_server, reset_mcp_state
from metaseed.facade.core import ProfileFacade
from metaseed.specs.builder import FIELD_MARKER_NAMES
from metaseed.specs.schema import ProfileSpec
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


class TestFieldConstraintsOverMcp:
    """`spec_update_field` merges constraints instead of replacing them.

    The tool's documented promise is that unset arguments keep their value. A
    field's eight constraints live in one object, so honoring that promise means
    merging, with an explicit `clear` list for removal.
    """

    def _constrained_draft(self, server):
        """A draft whose `Study.rating` carries enum, maximum and pattern."""
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        call(
            server,
            "spec_add_field",
            entity="Study",
            name="rating",
            field_type="string",
            enum=["low", "high"],
            maximum=10,
            pattern="^[a-z]+$",
        )

    @staticmethod
    def _field(server, entity, field_name):
        """Read a field back out of the draft as the client sees it (via YAML)."""
        spec = yaml.safe_load(get_tool(server, "spec_preview_yaml")())
        return next(
            f for f in spec["entities"][entity]["fields"] if f["name"] == field_name
        )

    def test_updating_one_constraint_keeps_the_others(self, server):
        """The regression: `minimum=1` must not wipe enum, maximum and pattern."""
        self._constrained_draft(server)

        call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="rating",
            minimum=1,
        )

        constraints = self._field(server, "Study", "rating")["constraints"]
        assert constraints["minimum"] == 1
        assert constraints["enum"] == ["low", "high"]
        assert constraints["maximum"] == 10
        assert constraints["pattern"] == "^[a-z]+$"

    def test_updating_another_attribute_keeps_constraints(self, server):
        self._constrained_draft(server)

        call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="rating",
            required=True,
        )

        field = self._field(server, "Study", "rating")
        assert field["required"] is True
        assert field["constraints"]["enum"] == ["low", "high"]

    def test_clear_removes_only_the_named_constraint(self, server):
        self._constrained_draft(server)

        call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="rating",
            clear=["maximum"],
        )

        constraints = self._field(server, "Study", "rating")["constraints"]
        assert "maximum" not in constraints
        assert constraints["enum"] == ["low", "high"]
        assert constraints["pattern"] == "^[a-z]+$"

    def test_set_and_clear_in_one_call(self, server):
        self._constrained_draft(server)

        call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="rating",
            minimum=0,
            clear=["enum", "pattern"],
        )

        constraints = self._field(server, "Study", "rating")["constraints"]
        assert constraints["minimum"] == 0
        assert constraints["maximum"] == 10
        assert "enum" not in constraints
        assert "pattern" not in constraints

    def test_clearing_the_last_constraint_drops_the_block(self, server):
        call(server, "spec_create", name="p", version="0.1")
        call(server, "spec_add_entity", name="Study")
        call(
            server,
            "spec_add_field",
            entity="Study",
            name="rating",
            field_type="string",
            maximum=10,
        )

        call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="rating",
            clear=["maximum"],
        )

        assert "constraints" not in self._field(server, "Study", "rating")

    def test_merging_onto_a_field_without_constraints_creates_them(self, server):
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
            max_length=50,
        )

        assert self._field(server, "Study", "title")["constraints"]["max_length"] == 50

    def test_unknown_clear_name_reports_the_valid_options(self, server):
        self._constrained_draft(server)

        result = call(
            server,
            "spec_update_field",
            entity="Study",
            field_name="rating",
            clear=["maxmium"],
        )

        assert "maxmium" in result["error"]
        assert "maximum" in result["error"]
        assert "enum" in result["error"]
        # the bad call left the field untouched
        assert self._field(server, "Study", "rating")["constraints"]["maximum"] == 10


class TestFieldMarkersOverMcp:
    """#210: the declarative field markers are reachable from the MCP tools.

    They were settable in the spec and in the web field editor but not here, so a
    profile built through an MCP client could not declare its own identifier.
    """

    @staticmethod
    def _field(server, entity, field_name):
        spec = yaml.safe_load(get_tool(server, "spec_preview_yaml")())
        return next(
            f for f in spec["entities"][entity]["fields"] if f["name"] == field_name
        )

    @staticmethod
    def _content_hash(server):
        spec = ProfileSpec.model_validate(
            yaml.safe_load(get_tool(server, "spec_preview_yaml")())
        )
        return spec.content_hash

    def _draft(self, server):
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(server, "spec_add_field", entity="Assay", name="f", field_type="string")

    def test_every_marker_is_a_parameter_of_both_field_tools(self, server):
        """Drift gate: a new FieldSpec marker must reach the tools, or be excluded."""
        for tool in ("spec_add_field", "spec_update_field"):
            parameters = inspect.signature(get_tool(server, tool)).parameters
            missing = [n for n in FIELD_MARKER_NAMES if n not in parameters]
            assert not missing, f"{tool} does not expose {missing}"

    @pytest.mark.parametrize(
        ("marker", "value"),
        [
            ("is_identifier", True),
            ("is_label", True),
            ("owns", True),
            ("tier", "recommended"),
            ("label", "Assay name"),
            ("unit", "cm"),
            ("example", "leaf area"),
            ("options", ["a", "b"]),
            ("codename", "assayName"),
            ("ontologies", ["po"]),
            ("unique_within", "parent"),
            ("dcat", "dct:title"),
        ],
    )
    def test_marker_set_on_add_survives_a_yaml_round_trip(self, server, marker, value):
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(
            server,
            "spec_add_field",
            entity="Assay",
            name="f",
            field_type="string",
            **{marker: value},
        )

        assert self._field(server, "Assay", "f")[marker] == value

        # Re-import the rendered YAML: the marker must survive a full round trip.
        call(
            server,
            "spec_import_yaml",
            yaml_text=get_tool(server, "spec_preview_yaml")(),
        )
        assert self._field(server, "Assay", "f")[marker] == value

    def test_marker_can_be_set_by_update(self, server):
        self._draft(server)

        call(
            server,
            "spec_update_field",
            entity="Assay",
            field_name="f",
            is_identifier=True,
        )

        assert self._field(server, "Assay", "f")["is_identifier"] is True

    def test_an_unset_marker_is_left_alone_on_update(self, server):
        """The tool's promise: an omitted argument keeps its current value."""
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(
            server,
            "spec_add_field",
            entity="Assay",
            name="f",
            field_type="string",
            is_identifier=True,
            unit="cm",
            tier="recommended",
        )

        call(server, "spec_update_field", entity="Assay", field_name="f", label="Area")

        field = self._field(server, "Assay", "f")
        assert field["is_identifier"] is True
        assert field["unit"] == "cm"
        assert field["tier"] == "recommended"
        assert field["label"] == "Area"

    @pytest.mark.parametrize(
        ("marker", "initial", "empty"),
        [
            ("is_identifier", True, False),
            ("unit", "cm", ""),
            ("options", ["x"], []),
        ],
    )
    def test_an_explicit_empty_value_unsets_a_marker(
        self, server, marker, initial, empty
    ):
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(
            server,
            "spec_add_field",
            entity="Assay",
            name="f",
            field_type="string",
            **{marker: initial},
        )

        call(
            server,
            "spec_update_field",
            entity="Assay",
            field_name="f",
            **{marker: empty},
        )

        # Unset means absent, not `false`/`""` -- otherwise the hash records the toggle.
        assert marker not in self._field(server, "Assay", "f")

    def test_setting_a_marker_changes_the_content_hash(self, server):
        self._draft(server)
        before = self._content_hash(server)

        call(server, "spec_update_field", entity="Assay", field_name="f", unit="cm")

        assert self._content_hash(server) != before

    def test_a_no_op_update_leaves_the_content_hash_alone(self, server):
        self._draft(server)
        before = self._content_hash(server)

        call(server, "spec_update_field", entity="Assay", field_name="f")

        assert self._content_hash(server) == before

    def test_a_bad_tier_is_rejected_without_touching_the_draft(self, server):
        self._draft(server)
        before = self._content_hash(server)

        result = call(
            server,
            "spec_update_field",
            entity="Assay",
            field_name="f",
            tier="mandatory",
            unit="cm",
        )

        assert "tier" in result["error"]
        assert self._content_hash(server) == before

    def test_a_declared_identifier_beats_positional_inference(self, server):
        """End to end through the tools: what the facade resolves must follow the mark."""
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(server, "spec_set_root_entity", entity="Assay")
        call(
            server, "spec_add_field", entity="Assay", name="input", field_type="string"
        )
        call(
            server,
            "spec_add_field",
            entity="Assay",
            name="file_name",
            field_type="string",
            is_identifier=True,
        )

        spec = ProfileSpec.model_validate(
            yaml.safe_load(get_tool(server, "spec_preview_yaml")())
        )
        facade = ProfileFacade(spec.name, spec.version, spec=spec)

        # `input` is positionally first and would win without the marker.
        assert facade.Assay.identifier_field == "file_name"


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

    def test_validate_warns_about_a_weak_inferred_identifier(self, server):
        """#210: inference always yields something, so a meaningless identity
        was reported as simply valid."""
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(server, "spec_set_root_entity", entity="Assay")
        call(
            server,
            "spec_add_field",
            entity="Assay",
            name="variable_name",
            field_type="string",
        )

        result = call(server, "spec_validate")

        # Advisory, not a defect: the spec still builds.
        assert result["valid"] is True
        assert result["issues"] == []
        assert len(result["warnings"]) == 1
        assert "variable_name" in result["warnings"][0]

    def test_declaring_the_identifier_silences_the_warning(self, server):
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        call(server, "spec_set_root_entity", entity="Assay")
        call(
            server,
            "spec_add_field",
            entity="Assay",
            name="variable_name",
            field_type="string",
            is_identifier=True,
        )

        assert call(server, "spec_validate")["warnings"] == []

    def test_two_declared_identifiers_are_an_issue_not_a_warning(self, server):
        """Two markers make the spec unloadable, so it is a defect."""
        call(server, "spec_create", name="p", version="1.0")
        call(server, "spec_add_entity", name="Assay")
        for name in ("a", "b"):
            call(
                server,
                "spec_add_field",
                entity="Assay",
                name=name,
                field_type="string",
                is_identifier=True,
            )

        result = call(server, "spec_validate")

        assert result["valid"] is False
        assert any("is_identifier" in issue for issue in result["issues"])


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
