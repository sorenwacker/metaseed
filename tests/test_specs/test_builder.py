"""Tests for the SpecBuilder engine.

SpecBuilder is the shared domain layer for authoring profile specifications,
used by both the web UI and the MCP tools. These tests pin every mutation,
the reference cascade on rename, auto back-reference creation, YAML round-trip,
and full-build validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import metaseed.specs
from metaseed.specs.builder import SpecBuilder
from metaseed.specs.schema import Constraints, FieldType, ProfileSpec


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

    def test_from_template_keeps_the_source_version(self):
        """The clone is a derivative *of* 1.2, and must stay MAJOR.MINOR.

        A marker suffix would make the draft unloadable: ProfileSpec.version is
        MAJOR.MINOR, so a suffixed draft could be saved but never read back.
        """
        builder = SpecBuilder.from_template("miappe", "1.2")

        assert builder.spec.version == "1.2"

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


class TestFieldConstraints:
    """Partial edits of the eight-valued ``FieldSpec.constraints`` object.

    ``constraints`` is one attribute holding eight values, so assigning it (what
    ``update_field`` does) is a wholesale replacement. ``update_field_constraints``
    is the merging path; these tests pin both semantics against each other.
    """

    @staticmethod
    def _builder_with_constrained_field() -> SpecBuilder:
        """A ``Study.rating`` carrying enum, maximum and pattern."""
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field(
            "Study",
            "rating",
            FieldType.STRING,
            constraints=Constraints(
                enum=["low", "high"], maximum=10, pattern="^[a-z]+$"
            ),
        )
        return builder

    @staticmethod
    def _rating(builder: SpecBuilder):
        return next(
            f for f in builder.spec.entities["Study"].fields if f.name == "rating"
        )

    def test_merge_preserves_constraints_that_were_not_supplied(self):
        """The regression: editing one constraint must not drop the other seven."""
        builder = self._builder_with_constrained_field()

        builder.update_field_constraints("Study", "rating", minimum=1)

        constraints = self._rating(builder).constraints
        assert constraints is not None
        assert constraints.minimum == 1
        assert constraints.enum == ["low", "high"]
        assert constraints.maximum == 10
        assert constraints.pattern == "^[a-z]+$"

    def test_clear_removes_only_the_named_constraint(self):
        builder = self._builder_with_constrained_field()

        builder.update_field_constraints("Study", "rating", clear=["maximum"])

        constraints = self._rating(builder).constraints
        assert constraints is not None
        assert constraints.maximum is None
        assert constraints.enum == ["low", "high"]
        assert constraints.pattern == "^[a-z]+$"

    def test_set_and_clear_in_one_call(self):
        builder = self._builder_with_constrained_field()

        builder.update_field_constraints(
            "Study", "rating", minimum=0, clear=["enum", "pattern"]
        )

        constraints = self._rating(builder).constraints
        assert constraints is not None
        assert constraints.minimum == 0
        assert constraints.enum is None
        assert constraints.pattern is None
        assert constraints.maximum == 10

    def test_setting_and_clearing_the_same_name_raises(self):
        builder = self._builder_with_constrained_field()

        with pytest.raises(ValueError, match="minimum"):
            builder.update_field_constraints(
                "Study", "rating", minimum=1, clear=["minimum"]
            )

    def test_clearing_the_last_constraint_leaves_none(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field(
            "Study", "rating", FieldType.STRING, constraints=Constraints(maximum=10)
        )

        builder.update_field_constraints("Study", "rating", clear=["maximum"])

        assert self._rating(builder).constraints is None

    def test_cleared_field_hashes_like_one_that_never_had_constraints(self):
        """An all-None Constraints and None must not be two different documents.

        ``canonical_json`` dumps with ``exclude_none=True``: an empty Constraints
        survives as an empty mapping while None drops out, so leaving the object
        behind would give the same spec two content hashes.
        """
        edited = SpecBuilder.empty("p", "0.1")
        edited.add_entity("Study")
        edited.add_field(
            "Study", "rating", FieldType.STRING, constraints=Constraints(maximum=10)
        )
        edited.update_field_constraints("Study", "rating", clear=["maximum"])

        pristine = SpecBuilder.empty("p", "0.1")
        pristine.add_entity("Study")
        pristine.add_field("Study", "rating", FieldType.STRING)

        assert edited.spec.content_hash == pristine.spec.content_hash

    def test_unknown_clear_name_raises_listing_valid_names(self):
        builder = self._builder_with_constrained_field()

        with pytest.raises(ValueError) as exc:
            builder.update_field_constraints("Study", "rating", clear=["maxmium"])

        message = str(exc.value)
        assert "maxmium" in message
        for name in (
            "pattern",
            "min_length",
            "max_length",
            "minimum",
            "maximum",
            "min_items",
            "max_items",
            "enum",
        ):
            assert name in message

    def test_unknown_constraint_value_raises(self):
        builder = self._builder_with_constrained_field()

        with pytest.raises(ValueError, match="nonsense"):
            builder.update_field_constraints("Study", "rating", nonsense=1)

    def test_merge_creates_constraints_when_the_field_has_none(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "title", FieldType.STRING)

        builder.update_field_constraints("Study", "title", max_length=50)

        field = next(
            f for f in builder.spec.entities["Study"].fields if f.name == "title"
        )
        assert field.constraints is not None
        assert field.constraints.max_length == 50

    def test_merge_on_missing_field_raises(self):
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")

        with pytest.raises(ValueError):
            builder.update_field_constraints("Study", "nope", minimum=1)

    def test_update_field_replaces_the_whole_constraints_object(self):
        """Pin the documented replace semantics of ``update_field``.

        This is not the bug; it is the deliberate other half of the pair, and the
        docstring must say so.
        """
        builder = self._builder_with_constrained_field()

        builder.update_field("Study", "rating", constraints=Constraints(minimum=1))

        constraints = self._rating(builder).constraints
        assert constraints is not None
        assert constraints.minimum == 1
        assert constraints.enum is None
        assert constraints.maximum is None
        assert constraints.pattern is None

    def test_update_field_docstring_states_the_replacement(self):
        doc = SpecBuilder.update_field.__doc__ or ""
        assert "constraints" in doc
        assert "update_field_constraints" in doc


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

    def test_list_field_without_items_reported(self):
        builder = SpecBuilder.empty("movies", "1.0")
        builder.add_entity("Movie")
        builder.set_root_entity("Movie")
        builder.add_field("Movie", "title", FieldType.STRING)
        builder.add_field("Movie", "tags", FieldType.LIST)

        issues = builder.validate()
        assert any("Movie.tags" in issue and "no 'items'" in issue for issue in issues)

    def test_entity_field_without_items_reported(self):
        builder = SpecBuilder.empty("movies", "1.0")
        builder.add_entity("Movie")
        builder.set_root_entity("Movie")
        builder.add_field("Movie", "director", FieldType.ENTITY)

        issues = builder.validate()
        assert any(
            "Movie.director" in issue and "no 'items'" in issue for issue in issues
        )

    def test_list_field_with_primitive_items_is_clean(self):
        """``items: string`` is a valid element type, not a missing target."""
        builder = SpecBuilder.empty("movies", "1.0")
        builder.add_entity("Movie")
        builder.set_root_entity("Movie")
        builder.add_field("Movie", "tags", FieldType.LIST, items="string")

        assert builder.validate() == []

    def test_blank_items_counts_as_missing_not_as_a_dangling_target(self):
        builder = SpecBuilder.empty("movies", "1.0")
        builder.add_entity("Movie")
        builder.set_root_entity("Movie")
        builder.add_field("Movie", "tags", FieldType.LIST, items="   ")

        issues = builder.validate()
        assert any("Movie.tags" in issue and "no 'items'" in issue for issue in issues)
        assert not any("is not a defined entity" in issue for issue in issues)


def _shipped_profiles() -> list[tuple[str, str]]:
    """Every ``profile.yaml`` shipped in the package, as (profile, version).

    Raises:
        RuntimeError: If none are found, which would leave the gate below
            parametrized with nothing and passing without testing anything.
    """
    specs_dir = Path(metaseed.specs.__file__).parent
    profiles = sorted(
        (path.parent.parent.name, path.parent.name)
        for path in specs_dir.glob("*/*/profile.yaml")
    )
    if not profiles:
        raise RuntimeError(f"No shipped profiles found under {specs_dir}")
    return profiles


_SHIPPED_PROFILES = _shipped_profiles()


@pytest.mark.parametrize(
    ("profile", "version"),
    _SHIPPED_PROFILES,
    ids=[f"{p}-{v}" for p, v in _SHIPPED_PROFILES],
)
def test_shipped_profile_validates_clean(profile: str, version: str) -> None:
    """Every shipped profile must satisfy every rule ``validate()`` enforces.

    A rule that the package's own profiles violate is either a wrong rule or a
    broken profile; this gate forces that to be decided when the rule is added,
    not discovered by a user authoring against a profile as a template.
    """
    assert SpecBuilder.from_template(profile, version).validate() == []


def _list_field(name: str, items: str):
    """Build a nested list FieldSpec pointing at ``items`` for tests."""
    from metaseed.specs.schema import FieldSpec

    return FieldSpec(name=name, type=FieldType.LIST, items=items)


class TestUpdateFieldValidatesLikeUpdateRule:
    """update_field must rebuild through the model, as update_rule does.

    Plain setattr bypassed every field_validator and the entity-level
    single-identifier invariant, so an invalid isa_tag or a second
    is_identifier field was accepted silently and the defect surfaced only
    when the saved YAML refused to load back.
    """

    def _builder(self) -> SpecBuilder:
        builder = SpecBuilder.empty("p", "0.1")
        builder.add_entity("Study")
        builder.add_field("Study", "title", FieldType.STRING)
        builder.add_field("Study", "code", FieldType.STRING)
        return builder

    def test_an_invalid_isa_tag_is_rejected(self):
        builder = self._builder()
        with pytest.raises(ValueError):
            builder.update_field("Study", "title", isa_tag="not-a-tag")

    def test_a_second_identifier_is_rejected(self):
        builder = self._builder()
        builder.update_field("Study", "title", is_identifier=True)
        with pytest.raises(ValueError):
            builder.update_field("Study", "code", is_identifier=True)

    def test_a_failed_update_changes_nothing(self):
        builder = self._builder()
        with pytest.raises(ValueError):
            builder.update_field(
                "Study", "title", description="kept?", isa_tag="not-a-tag"
            )
        field = next(
            f for f in builder.spec.entities["Study"].fields if f.name == "title"
        )
        assert field.description != "kept?"
        assert field.isa_tag is None
