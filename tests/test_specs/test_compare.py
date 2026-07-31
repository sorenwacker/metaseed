"""Breaking-change classification between two versions of a profile spec.

Every classification branch documented in
docs/api/schema-specs.md#profile-versioning has a case here. The specs are
synthesized in-process; nothing reads the user's spec directory.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from metaseed.specs.compare import (
    COMPATIBILITY_BY_KIND,
    COSMETIC_FIELD_ATTRIBUTES,
    SEMANTIC_FIELD_ATTRIBUTES,
    ChangeKind,
    Compatibility,
    SpecChange,
    compare_specs,
    required_bump,
)
from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    SeekEntityConfig,
    ValidationRuleSpec,
)


def base() -> ProfileSpec:
    """A small two-entity profile used as the `old` side of most comparisons."""
    return ProfileSpec(
        name="cinema",
        version="1.0",
        display_name="Cinema",
        root_entity="Film",
        entities={
            "Film": EntityDefSpec(
                description="A motion picture",
                fields=[
                    FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                    FieldSpec(name="title", type=FieldType.STRING),
                    FieldSpec(name="runtime_minutes", type=FieldType.INTEGER),
                    FieldSpec(name="credits", type=FieldType.LIST, items="Credit"),
                ],
            ),
            "Credit": EntityDefSpec(
                description="A person's contribution to a film",
                fields=[
                    FieldSpec(
                        name="film_id",
                        type=FieldType.STRING,
                        required=True,
                        reference="Film.identifier",
                    ),
                    FieldSpec(name="person", type=FieldType.STRING),
                    FieldSpec(name="role", type=FieldType.STRING),
                ],
            ),
        },
    )


def field_of(spec: ProfileSpec, entity: str, name: str) -> FieldSpec:
    """The named field, so a test can mutate it directly."""
    return next(f for f in spec.entities[entity].fields if f.name == name)


def changes(old: ProfileSpec, new: ProfileSpec) -> list[SpecChange]:
    return list(compare_specs(old, new).changes)


def only(old: ProfileSpec, new: ProfileSpec) -> SpecChange:
    """The single change between two specs, asserting there is exactly one."""
    found = changes(old, new)
    assert len(found) == 1, f"expected one change, got {[c.message for c in found]}"
    return found[0]


class TestTheClassificationTableIsTotal:
    """Gates against a kind or a field attribute slipping through unclassified."""

    def test_every_change_kind_has_a_compatibility(self) -> None:
        assert set(COMPATIBILITY_BY_KIND) == set(ChangeKind)

    def test_every_field_attribute_is_either_handled_or_bucketed(self) -> None:
        handled = {"name", "type", "required", "items", "constraints"}

        assert (handled | COSMETIC_FIELD_ATTRIBUTES | SEMANTIC_FIELD_ATTRIBUTES) == set(
            FieldSpec.model_fields
        )
        assert not (COSMETIC_FIELD_ATTRIBUTES & SEMANTIC_FIELD_ATTRIBUTES)


# ----------------------------------------------------------------------
# Breaking changes
# ----------------------------------------------------------------------
class TestBreaking:
    def test_root_entity_changed(self) -> None:
        new = base()
        new.root_entity = "Credit"

        change = only(base(), new)
        assert change.kind == ChangeKind.ROOT_ENTITY_CHANGED
        assert change.compatibility is Compatibility.BREAKING

    def test_entity_removed(self) -> None:
        new = base()
        del new.entities["Credit"]

        change = only(base(), new)
        assert change.kind == ChangeKind.ENTITY_REMOVED
        assert change.target == "Credit"
        assert change.compatibility is Compatibility.BREAKING

    def test_field_removed(self) -> None:
        new = base()
        new.entities["Credit"].fields = [
            f for f in new.entities["Credit"].fields if f.name != "role"
        ]

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELD_REMOVED
        assert change.target == "Credit.role"
        assert change.compatibility is Compatibility.BREAKING

    def test_required_field_added(self) -> None:
        new = base()
        new.entities["Credit"].fields.append(
            FieldSpec(name="billing_order", type=FieldType.INTEGER, required=True)
        )

        change = only(base(), new)
        assert change.kind == ChangeKind.REQUIRED_FIELD_ADDED
        assert change.compatibility is Compatibility.BREAKING

    def test_optional_field_became_required(self) -> None:
        new = base()
        field_of(new, "Credit", "person").required = True

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELD_BECAME_REQUIRED
        assert change.compatibility is Compatibility.BREAKING
        assert change.message == "Credit.person became required"

    def test_field_type_changed(self) -> None:
        new = base()
        field_of(new, "Film", "runtime_minutes").type = FieldType.STRING

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELD_TYPE_CHANGED
        assert change.compatibility is Compatibility.BREAKING
        assert "integer" in change.message and "string" in change.message

    def test_nesting_link_retargeted(self) -> None:
        new = base()
        new.entities["Person"] = EntityDefSpec(description="A person")
        field_of(new, "Film", "credits").items = "Person"

        found = [c for c in changes(base(), new) if c.target == "Film.credits"]
        assert [c.kind for c in found] == [ChangeKind.NESTING_RETARGETED]
        assert found[0].compatibility is Compatibility.BREAKING

    def test_nesting_link_removed(self) -> None:
        new = base()
        field_of(new, "Film", "credits").items = None

        change = only(base(), new)
        assert change.kind == ChangeKind.NESTING_REMOVED
        assert change.compatibility is Compatibility.BREAKING

    def test_enum_values_removed(self) -> None:
        old = base()
        field_of(old, "Credit", "role").constraints = Constraints(
            enum=["director", "actor", "writer"]
        )
        new = copy.deepcopy(old)
        field_of(new, "Credit", "role").constraints = Constraints(
            enum=["director", "actor"]
        )

        change = only(old, new)
        assert change.kind == ChangeKind.ENUM_NARROWED
        assert change.compatibility is Compatibility.BREAKING
        assert "writer" in change.message

    def test_enum_introduced_where_there_was_none(self) -> None:
        new = base()
        field_of(new, "Credit", "role").constraints = Constraints(enum=["director"])

        change = only(base(), new)
        assert change.kind == ChangeKind.ENUM_NARROWED
        assert change.compatibility is Compatibility.BREAKING

    @pytest.mark.parametrize(
        ("entity", "field", "old_kw", "new_kw"),
        [
            ("Film", "runtime_minutes", {"minimum": 1}, {"minimum": 30}),
            ("Film", "runtime_minutes", {}, {"minimum": 30}),
            ("Film", "runtime_minutes", {"maximum": 500}, {"maximum": 300}),
            ("Film", "runtime_minutes", {}, {"maximum": 300}),
            ("Credit", "role", {"min_length": 2}, {"min_length": 5}),
            ("Credit", "role", {}, {"min_length": 5}),
            ("Credit", "role", {"max_length": 50}, {"max_length": 20}),
            ("Credit", "role", {}, {"max_length": 20}),
            ("Film", "credits", {"min_items": 1}, {"min_items": 2}),
            ("Film", "credits", {}, {"min_items": 2}),
            ("Film", "credits", {"max_items": 50}, {"max_items": 10}),
            ("Film", "credits", {}, {"max_items": 10}),
        ],
    )
    def test_bounds_tightened(
        self, entity: str, field: str, old_kw: dict[str, Any], new_kw: dict[str, Any]
    ) -> None:
        old = base()
        if old_kw:
            field_of(old, entity, field).constraints = Constraints(**old_kw)
        new = copy.deepcopy(old)
        field_of(new, entity, field).constraints = Constraints(**new_kw)

        change = only(old, new)
        assert change.kind == ChangeKind.CONSTRAINT_TIGHTENED
        assert change.compatibility is Compatibility.BREAKING
        assert next(iter(new_kw)) in change.message

    def test_pattern_added(self) -> None:
        new = base()
        field_of(new, "Credit", "role").constraints = Constraints(pattern="^[a-z]+$")

        change = only(base(), new)
        assert change.kind == ChangeKind.PATTERN_TIGHTENED
        assert change.compatibility is Compatibility.BREAKING

    def test_pattern_changed_is_treated_as_stricter(self) -> None:
        old = base()
        field_of(old, "Credit", "role").constraints = Constraints(pattern="^[a-z]+$")
        new = copy.deepcopy(old)
        field_of(new, "Credit", "role").constraints = Constraints(pattern="^[a-z]{3}$")

        change = only(old, new)
        assert change.kind == ChangeKind.PATTERN_TIGHTENED
        assert change.compatibility is Compatibility.BREAKING

    def test_validation_rule_added(self) -> None:
        new = base()
        new.validation_rules.append(
            ValidationRuleSpec(name="role_known", field="role", enum=["director"])
        )

        change = only(base(), new)
        assert change.kind == ChangeKind.VALIDATION_RULE_ADDED
        assert change.compatibility is Compatibility.BREAKING

    def test_validation_rule_changed(self) -> None:
        old = base()
        old.validation_rules.append(
            ValidationRuleSpec(name="role_known", field="role", enum=["director"])
        )
        new = copy.deepcopy(old)
        new.validation_rules[0].enum = ["director", "actor"]

        change = only(old, new)
        assert change.kind == ChangeKind.VALIDATION_RULE_CHANGED
        assert change.compatibility is Compatibility.BREAKING

    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            ("reference", "Credit.person"),
            ("parent_ref", "Film.title"),
            ("unique_within", "parent"),
            ("owns", True),
            ("is_identifier", True),
            ("options", ["director"]),
        ],
    )
    def test_an_unclassified_semantic_attribute_defaults_to_breaking(
        self, attribute: str, value: object
    ) -> None:
        new = base()
        setattr(field_of(new, "Credit", "role"), attribute, value)

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELD_CHANGED
        assert change.compatibility is Compatibility.BREAKING
        assert attribute in change.message


# ----------------------------------------------------------------------
# Compatible changes
# ----------------------------------------------------------------------
class TestCompatible:
    def test_entity_added(self) -> None:
        new = base()
        new.entities["Studio"] = EntityDefSpec(description="A production company")

        change = only(base(), new)
        assert change.kind == ChangeKind.ENTITY_ADDED
        assert change.compatibility is Compatibility.COMPATIBLE

    def test_optional_field_added(self) -> None:
        new = base()
        new.entities["Credit"].fields.append(
            FieldSpec(name="billing_order", type=FieldType.INTEGER)
        )

        change = only(base(), new)
        assert change.kind == ChangeKind.OPTIONAL_FIELD_ADDED
        assert change.compatibility is Compatibility.COMPATIBLE

    def test_required_field_became_optional(self) -> None:
        new = base()
        field_of(new, "Film", "identifier").required = False

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELD_BECAME_OPTIONAL
        assert change.compatibility is Compatibility.COMPATIBLE

    def test_enum_widened(self) -> None:
        old = base()
        field_of(old, "Credit", "role").constraints = Constraints(enum=["director"])
        new = copy.deepcopy(old)
        field_of(new, "Credit", "role").constraints = Constraints(
            enum=["director", "actor"]
        )

        change = only(old, new)
        assert change.kind == ChangeKind.ENUM_WIDENED
        assert change.compatibility is Compatibility.COMPATIBLE

    def test_enum_dropped(self) -> None:
        old = base()
        field_of(old, "Credit", "role").constraints = Constraints(enum=["director"])
        new = copy.deepcopy(old)
        field_of(new, "Credit", "role").constraints = None

        change = only(old, new)
        assert change.kind == ChangeKind.ENUM_WIDENED
        assert change.compatibility is Compatibility.COMPATIBLE

    @pytest.mark.parametrize(
        ("entity", "field", "old_kw", "new_kw"),
        [
            ("Film", "runtime_minutes", {"minimum": 30}, {"minimum": 1}),
            ("Film", "runtime_minutes", {"minimum": 30}, {}),
            ("Film", "runtime_minutes", {"maximum": 300}, {"maximum": 500}),
            ("Film", "runtime_minutes", {"maximum": 300}, {}),
            ("Credit", "role", {"min_length": 5}, {"min_length": 2}),
            ("Credit", "role", {"min_length": 5}, {}),
            ("Credit", "role", {"max_length": 20}, {"max_length": 50}),
            ("Credit", "role", {"max_length": 20}, {}),
            ("Film", "credits", {"min_items": 2}, {"min_items": 1}),
            ("Film", "credits", {"min_items": 2}, {}),
            ("Film", "credits", {"max_items": 10}, {"max_items": 50}),
            ("Film", "credits", {"max_items": 10}, {}),
        ],
    )
    def test_bounds_loosened(
        self, entity: str, field: str, old_kw: dict[str, Any], new_kw: dict[str, Any]
    ) -> None:
        old = base()
        field_of(old, entity, field).constraints = Constraints(**old_kw)
        new = copy.deepcopy(old)
        field_of(new, entity, field).constraints = (
            Constraints(**new_kw) if new_kw else None
        )

        change = only(old, new)
        assert change.kind == ChangeKind.CONSTRAINT_LOOSENED
        assert change.compatibility is Compatibility.COMPATIBLE
        assert next(iter(old_kw)) in change.message

    def test_pattern_removed(self) -> None:
        old = base()
        field_of(old, "Credit", "role").constraints = Constraints(pattern="^[a-z]+$")
        new = copy.deepcopy(old)
        field_of(new, "Credit", "role").constraints = None

        change = only(old, new)
        assert change.kind == ChangeKind.PATTERN_RELAXED
        assert change.compatibility is Compatibility.COMPATIBLE

    def test_fields_reordered(self) -> None:
        new = base()
        fields = new.entities["Credit"].fields
        fields[1], fields[2] = fields[2], fields[1]

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELDS_REORDERED
        assert change.target == "Credit"
        assert change.compatibility is Compatibility.COMPATIBLE

    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            ("description", "The role played"),
            ("ontology_term", "OBI:0000112"),
            ("label", "Role"),
            ("codename", "creditRole"),
            ("example", "director"),
            ("unit", "none"),
            ("tier", "recommended"),
            ("dcat", "dct:title"),
            ("is_label", True),
        ],
    )
    def test_field_metadata_changed(self, attribute: str, value: object) -> None:
        new = base()
        setattr(field_of(new, "Credit", "role"), attribute, value)

        change = only(base(), new)
        assert change.kind == ChangeKind.FIELD_METADATA_CHANGED
        assert change.compatibility is Compatibility.COMPATIBLE
        assert attribute in change.message

    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            ("description", "Anyone credited on a film"),
            ("ontology_term", "OBI:0000245"),
            ("example", {"role": "director"}),
            ("seek", SeekEntityConfig(role="Assay")),
        ],
    )
    def test_entity_metadata_changed(self, attribute: str, value: object) -> None:
        new = base()
        setattr(new.entities["Credit"], attribute, value)

        change = only(base(), new)
        assert change.kind == ChangeKind.ENTITY_METADATA_CHANGED
        assert change.target == "Credit"
        assert change.compatibility is Compatibility.COMPATIBLE

    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            ("display_name", "Cinema Profile"),
            ("description", "Films and who made them"),
            ("ontology", "OBI"),
        ],
    )
    def test_profile_metadata_changed(self, attribute: str, value: object) -> None:
        new = base()
        setattr(new, attribute, value)

        change = only(base(), new)
        assert change.kind == ChangeKind.PROFILE_METADATA_CHANGED
        assert change.compatibility is Compatibility.COMPATIBLE

    def test_validation_rule_removed(self) -> None:
        old = base()
        old.validation_rules.append(ValidationRuleSpec(name="role_known"))
        new = copy.deepcopy(old)
        new.validation_rules = []

        change = only(old, new)
        assert change.kind == ChangeKind.VALIDATION_RULE_REMOVED
        assert change.compatibility is Compatibility.COMPATIBLE


# ----------------------------------------------------------------------
# The bump rule
# ----------------------------------------------------------------------
class TestRequiredBump:
    def test_identical_content_requires_no_bump(self) -> None:
        assert required_bump(base(), base()) == "none"

    def test_the_version_field_itself_is_not_a_change(self) -> None:
        new = base()
        new.version = "9.9"

        assert changes(base(), new) == []
        assert required_bump(base(), new) == "none"

    def test_the_spec_format_version_is_not_a_profile_change(self) -> None:
        new = base()
        new.spec_version = "0.6"

        assert changes(base(), new) == []

    def test_compatible_changes_alone_require_a_minor_bump(self) -> None:
        new = base()
        new.entities["Studio"] = EntityDefSpec(description="A production company")

        assert required_bump(base(), new) == "minor"

    def test_one_breaking_change_requires_a_major_bump(self) -> None:
        new = base()
        new.entities["Studio"] = EntityDefSpec(description="A production company")
        field_of(new, "Credit", "person").required = True

        assert required_bump(base(), new) == "major"


class TestComparisonSurface:
    def test_the_comparison_partitions_and_reports_the_bump(self) -> None:
        new = base()
        new.entities["Studio"] = EntityDefSpec(description="A production company")
        field_of(new, "Credit", "person").required = True

        comparison = compare_specs(base(), new)

        assert len(comparison) == 2
        assert {c.kind for c in comparison.breaking} == {
            ChangeKind.FIELD_BECAME_REQUIRED
        }
        assert {c.kind for c in comparison.compatible} == {ChangeKind.ENTITY_ADDED}
        assert comparison.required_bump == "major"
        assert comparison.old_version == "1.0"
        assert comparison.new_version == "1.0"
        assert list(comparison) == list(comparison.changes)

    def test_every_change_renders_a_line_naming_its_target(self) -> None:
        new = base()
        del new.entities["Credit"]
        new.root_entity = "Studio"
        new.entities["Studio"] = EntityDefSpec(description="A production company")

        for change in compare_specs(base(), new):
            assert change.message
            assert str(change) == change.message

    def test_a_change_serializes_to_a_json_safe_dict(self) -> None:
        new = base()
        field_of(new, "Credit", "person").required = True

        payload = compare_specs(base(), new).to_dict()

        assert payload["required_bump"] == "major"
        assert payload["breaking"][0] == {
            "kind": "field_became_required",
            "compatibility": "breaking",
            "target": "Credit.person",
            "message": "Credit.person became required",
            "old": False,
            "new": True,
        }


class TestCinemaOnePointOne:
    """The change that started this: a 1.0 -> 1.1 bump that was really major.

    `Credit.person` became required and `Credit.role` was narrowed to an enum, so
    a dataset valid under 1.0 can fail under 1.1.
    """

    def old(self) -> ProfileSpec:
        return base()

    def new(self) -> ProfileSpec:
        spec = base()
        spec.version = "1.1"
        field_of(spec, "Credit", "person").required = True
        field_of(spec, "Credit", "role").constraints = Constraints(
            enum=["director", "actor", "writer"]
        )
        return spec

    def test_the_bump_should_have_been_major(self) -> None:
        assert required_bump(self.old(), self.new()) == "major"

    def test_both_breaking_changes_are_reported(self) -> None:
        comparison = compare_specs(self.old(), self.new())

        assert [c.message for c in comparison.breaking] == [
            "Credit.person became required",
            "Credit.role restricted to an enum of 3 value(s): actor, director, writer",
        ]

    def test_the_two_versions_are_distinguishable_by_content_hash(self) -> None:
        assert self.old().content_hash != self.new().content_hash
