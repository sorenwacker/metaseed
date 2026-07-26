"""Tests for the SpecBuilder engine.

SpecBuilder is the shared domain layer for authoring profile specifications,
used by both the web UI and the MCP tools. These tests pin every mutation,
the reference cascade on rename, auto back-reference creation, YAML round-trip,
and full-build validation.
"""

from __future__ import annotations

import pytest

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.schema import FieldType, ProfileSpec


class TestConstruction:
    """Constructors that produce a draft spec."""

    def test_empty_creates_named_spec_without_entities(self):
        builder = SpecBuilder.empty("my-profile", "0.1")

        assert builder.spec.name == "my-profile"
        assert builder.spec.version == "0.1"
        assert builder.spec.entities == {}

    def test_empty_accepts_optional_metadata(self):
        builder = SpecBuilder.empty(
            "my-profile",
            "0.1",
            display_name="My Profile",
            description="A test profile",
            ontology="PPEO",
        )

        assert builder.spec.display_name == "My Profile"
        assert builder.spec.description == "A test profile"
        assert builder.spec.ontology == "PPEO"

    def test_from_template_clones_independent_copy(self):
        builder = SpecBuilder.from_template("miappe", "1.2")

        assert builder.spec.entities  # has entities from the template
        # mutating the clone must not affect the cached source
        builder.delete_entity(next(iter(builder.spec.entities)))
        other = SpecBuilder.from_template("miappe", "1.2")
        assert len(other.spec.entities) > len(builder.spec.entities)

    def test_from_template_marks_version_as_derivative(self):
        builder = SpecBuilder.from_template("miappe", "1.2")

        assert "-dev" in builder.spec.version

    def test_from_template_unknown_profile_raises(self):
        with pytest.raises(ValueError):
            SpecBuilder.from_template("does-not-exist", "9.9")

    def test_from_spec_wraps_existing(self):
        spec = ProfileSpec(name="wrapped", version="0.1")
        builder = SpecBuilder.from_spec(spec)

        assert builder.spec is spec


class TestProfileMetadata:
    """Profile-level fields and root entity."""

    def test_set_metadata_updates_fields(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.set_metadata(display_name="Renamed", description="desc")

        assert builder.spec.display_name == "Renamed"
        assert builder.spec.description == "desc"

    def test_set_root_entity_requires_existing_entity(self):
        builder = SpecBuilder.empty("p", "0.1")
        with pytest.raises(ValueError):
            builder.set_root_entity("Missing")

    def test_set_root_entity_succeeds_for_existing(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Investigation")
        builder.set_root_entity("Investigation")

        assert builder.spec.root_entity == "Investigation"


class TestEntities:
    """Entity add/update/rename/delete."""

    def test_add_entity(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study", description="A study", ontology_term="X:1")

        assert "Study" in builder.spec.entities
        assert builder.spec.entities["Study"].description == "A study"
        assert builder.spec.entities["Study"].ontology_term == "X:1"

    def test_add_duplicate_entity_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        with pytest.raises(ValueError):
            builder.add_entity("Study")

    def test_add_entity_rejects_invalid_name(self):
        builder = SpecBuilder.empty("p", "0.1")
        with pytest.raises(ValueError):
            builder.add_entity("lowercase")  # must be PascalCase

    def test_update_entity(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.update_entity("Study", description="new", ontology_term="Y:2")

        assert builder.spec.entities["Study"].description == "new"
        assert builder.spec.entities["Study"].ontology_term == "Y:2"

    def test_update_missing_entity_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        with pytest.raises(ValueError):
            builder.update_entity("Missing", description="x")

    def test_delete_entity(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.delete_entity("Study")

        assert "Study" not in builder.spec.entities

    def test_delete_missing_entity_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        with pytest.raises(ValueError):
            builder.delete_entity("Missing")

    def test_delete_root_entity_clears_root(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Investigation")
        builder.set_root_entity("Investigation")
        builder.delete_entity("Investigation")

        assert builder.spec.root_entity == ""


class TestRenameCascade:
    """rename_entity must rewrite every reference to the old name."""

    def _two_entity_builder(self) -> SpecBuilder:
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Investigation")
        builder.add_entity("Study")
        return builder

    def test_rename_updates_entity_key(self):
        builder = self._two_entity_builder()
        builder.rename_entity("Study", "Trial")

        assert "Trial" in builder.spec.entities
        assert "Study" not in builder.spec.entities

    def test_rename_updates_list_items(self):
        builder = self._two_entity_builder()
        builder.add_field("Investigation", "studies", FieldType.LIST, items="Study")

        builder.rename_entity("Study", "Trial")

        field = next(
            f
            for f in builder.spec.entities["Investigation"].fields
            if f.name == "studies"
        )
        assert field.items == "Trial"

    def test_rename_updates_reference_and_parent_ref(self):
        builder = self._two_entity_builder()
        builder.add_field(
            "Study",
            "inv_ref",
            FieldType.STRING,
            reference="Investigation.identifier",
            parent_ref="Investigation.identifier",
        )

        builder.rename_entity("Investigation", "Project")

        field = next(
            f for f in builder.spec.entities["Study"].fields if f.name == "inv_ref"
        )
        assert field.reference == "Project.identifier"
        assert field.parent_ref == "Project.identifier"

    def test_rename_updates_validation_rules(self):
        builder = self._two_entity_builder()
        builder.add_rule(
            "ref_rule",
            applies_to=["Study"],
            reference="Study.identifier",
        )

        builder.rename_entity("Study", "Trial")

        rule = builder.spec.validation_rules[0]
        assert rule.applies_to == ["Trial"]
        assert rule.reference == "Trial.identifier"

    def test_rename_to_existing_name_raises(self):
        builder = self._two_entity_builder()
        with pytest.raises(ValueError):
            builder.rename_entity("Study", "Investigation")


class TestFields:
    """Field add/update/delete/move and auto back-reference."""

    def test_add_basic_field(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "title", FieldType.STRING, required=True)

        field = builder.spec.entities["Study"].fields[-1]
        assert field.name == "title"
        assert field.type == FieldType.STRING
        assert field.required is True

    def test_add_field_to_missing_entity_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        with pytest.raises(ValueError):
            builder.add_field("Missing", "title", FieldType.STRING)

    def test_add_duplicate_field_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "title", FieldType.STRING)
        with pytest.raises(ValueError):
            builder.add_field("Study", "title", FieldType.STRING)

    def test_add_field_rejects_unknown_attribute(self):
        # add_field rejects unknown attributes with the same friendly ValueError
        # as update_field (rather than a raw pydantic ValidationError).
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        with pytest.raises(ValueError, match="Unknown field attribute"):
            builder.add_field("Study", "title", FieldType.STRING, bogus_attr=True)

    def test_add_nested_list_field_creates_back_reference(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Investigation")
        builder.add_entity("Study")

        builder.add_field("Investigation", "studies", FieldType.LIST, items="Study")

        # parent gains an identifier field
        inv_fields = {f.name for f in builder.spec.entities["Investigation"].fields}
        assert "identifier" in inv_fields
        # target gains a back-reference to the parent
        study_back_ref = [
            f
            for f in builder.spec.entities["Study"].fields
            if f.reference == "Investigation.identifier"
        ]
        assert len(study_back_ref) == 1

    def test_nested_field_respects_existing_is_identifier(self):
        """A parent that already designates an identifier must not gain a second.

        The back-reference machinery injected a required field literally named
        ``identifier`` whenever the parent had none by that name -- ignoring a
        field already marked ``is_identifier``. The parent then required both its
        real identifier and a phantom ``identifier``, so the generated model
        could not be instantiated. Respect the marker: inject nothing, and point
        the child's back-reference at the real identifier field.
        """
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Project")
        builder.add_field("Project", "project_id", FieldType.STRING, is_identifier=True)
        builder.add_entity("Item")

        builder.add_field("Project", "items", FieldType.LIST, items="Item")

        proj_fields = {f.name for f in builder.spec.entities["Project"].fields}
        assert "identifier" not in proj_fields  # no phantom field
        back_ref = [
            f
            for f in builder.spec.entities["Item"].fields
            if f.reference and f.reference.startswith("Project.")
        ]
        assert len(back_ref) == 1
        assert back_ref[0].reference == "Project.project_id"  # points at the real id

    def test_add_primitive_list_field_creates_no_back_reference(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "tags", FieldType.LIST, items="string")

        assert "identifier" not in {
            f.name for f in builder.spec.entities["Study"].fields
        }

    def test_update_field_by_name(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "title", FieldType.STRING)
        builder.update_field("Study", "title", required=True, description="The title")

        field = next(
            f for f in builder.spec.entities["Study"].fields if f.name == "title"
        )
        assert field.required is True
        assert field.description == "The title"

    def test_update_missing_field_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        with pytest.raises(ValueError):
            builder.update_field("Study", "nope", required=True)

    def test_delete_field_by_name(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "title", FieldType.STRING)
        builder.delete_field("Study", "title")

        assert "title" not in {f.name for f in builder.spec.entities["Study"].fields}

    def test_delete_missing_field_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        with pytest.raises(ValueError):
            builder.delete_field("Study", "nope")

    def test_move_field_changes_order(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "a", FieldType.STRING)
        builder.add_field("Study", "b", FieldType.STRING)

        builder.move_field("Study", "b", "up")

        names = [f.name for f in builder.spec.entities["Study"].fields]
        assert names == ["b", "a"]

    def test_move_field_at_boundary_is_noop(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "a", FieldType.STRING)
        builder.add_field("Study", "b", FieldType.STRING)

        builder.move_field("Study", "a", "up")  # already first

        names = [f.name for f in builder.spec.entities["Study"].fields]
        assert names == ["a", "b"]


class TestRules:
    """Validation rule add/update/delete by name."""

    def test_add_rule(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_rule("r1", message="must hold")

        assert builder.spec.validation_rules[0].name == "r1"
        assert builder.spec.validation_rules[0].message == "must hold"

    def test_add_duplicate_rule_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_rule("r1")
        with pytest.raises(ValueError):
            builder.add_rule("r1")

    def test_update_rule(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_rule("r1")
        builder.update_rule("r1", message="changed")

        assert builder.spec.validation_rules[0].message == "changed"

    def test_update_missing_rule_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        with pytest.raises(ValueError):
            builder.update_rule("nope", message="x")

    def test_delete_rule(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_rule("r1")
        builder.delete_rule("r1")

        assert builder.spec.validation_rules == []


class TestSerialization:
    """YAML round-trip."""

    def test_to_yaml_round_trips(self):
        builder = SpecBuilder.empty("p", "0.1", display_name="P")
        builder.add_entity("Study", description="A study")
        builder.add_field("Study", "title", FieldType.STRING, required=True)

        yaml_text = builder.to_yaml()
        restored = SpecBuilder.from_yaml(yaml_text)

        assert restored.spec.name == "p"
        assert restored.spec.entities["Study"].fields[0].name == "title"
        assert restored.spec.entities["Study"].fields[0].required is True

    def test_from_yaml_invalid_raises(self):
        with pytest.raises(ValueError):
            SpecBuilder.from_yaml("name: [unclosed")


class TestValidation:
    """validate() performs a full model build plus reference checks."""

    def test_real_template_validates_clean(self):
        builder = SpecBuilder.from_template("miappe", "1.2")

        assert builder.validate() == []

    def test_dangling_list_items_reported(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Investigation")
        # point a nested list at an entity that does not exist
        builder.spec.entities["Investigation"].fields.append(
            _list_field("studies", "Ghost")
        )

        issues = builder.validate()
        assert any("Ghost" in issue for issue in issues)

    def test_missing_root_entity_reported(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Investigation")
        builder.spec.root_entity = "Nonexistent"

        issues = builder.validate()
        assert any("root" in issue.lower() for issue in issues)


def _list_field(name: str, items: str):
    """Build a nested list FieldSpec pointing at ``items`` for tests."""
    from metaseed.specs.schema import FieldSpec

    return FieldSpec(name=name, type=FieldType.LIST, items=items)
