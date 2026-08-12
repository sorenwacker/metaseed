"""Tests for validation engine."""

import datetime

import pytest

from metaseed.specs.schema import ValidationRuleSpec
from metaseed.validators import validate
from metaseed.validators.engine import (
    ValidationEngine,
    _create_rule_from_spec,
    create_engine_for_entity,
)
from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    ListCardinalityRule,
    RequiredFieldsRule,
)


class TestValidationEngine:
    """Tests for ValidationEngine class."""

    def test_no_rules_no_errors(self) -> None:
        """No rules means no errors."""
        engine = ValidationEngine()
        errors = engine.validate({})
        assert len(errors) == 0

    def test_add_rule(self) -> None:
        """Rules can be added to engine."""
        engine = ValidationEngine()
        rule = RequiredFieldsRule(fields=["name"])
        engine.add_rule(rule)
        assert len(engine.rules) == 1

    def test_validate_with_single_rule(self) -> None:
        """Single rule is applied."""
        engine = ValidationEngine()
        engine.add_rule(RequiredFieldsRule(fields=["name"]))

        errors = engine.validate({"name": "Test"})
        assert len(errors) == 0

        errors = engine.validate({})
        assert len(errors) == 1

    def test_validate_with_multiple_rules(self) -> None:
        """Multiple rules are applied."""
        engine = ValidationEngine()
        engine.add_rule(RequiredFieldsRule(fields=["name"]))
        engine.add_rule(DateRangeRule(start_field="start", end_field="end"))

        data = {
            "name": "Test",
            "start": datetime.date(2024, 12, 31),
            "end": datetime.date(2024, 1, 1),
        }
        errors = engine.validate(data)
        assert len(errors) == 1  # Only date range error

        data = {}
        errors = engine.validate(data)
        assert len(errors) == 1  # Only required field error (dates missing = skipped)

    def test_errors_collected_from_all_rules(self) -> None:
        """Errors from all rules are collected."""
        engine = ValidationEngine()
        engine.add_rule(RequiredFieldsRule(fields=["name", "id"]))

        errors = engine.validate({})
        assert len(errors) == 2

    def test_chain_rules(self) -> None:
        """Rules can be chained with add_rule."""
        engine = (
            ValidationEngine()
            .add_rule(RequiredFieldsRule(fields=["name"]))
            .add_rule(RequiredFieldsRule(fields=["id"]))
        )
        assert len(engine.rules) == 2


class TestValidateFunction:
    """Tests for validate convenience function."""

    def test_validate_investigation(self) -> None:
        """Validate Investigation entity."""
        data = {
            "unique_id": "INV001",
            "title": "Test Investigation",
            "contacts": [{"name": "Test Contact"}],
            "studies": [
                {
                    "unique_id": "STU001",
                    "title": "Test Study",
                    "investigation_id": "INV001",
                }
            ],
        }
        errors = validate(data, "investigation", version="1.1")
        assert len(errors) == 0

    def test_validate_investigation_missing_required(self) -> None:
        """Validate Investigation with missing required fields."""
        data = {"unique_id": "INV001"}  # missing title
        errors = validate(data, "investigation", version="1.1")
        assert len(errors) >= 1
        assert any("title" in e.field for e in errors)

    def test_validate_study_date_range(self) -> None:
        """Validate Study with date range."""
        data = {
            "unique_id": "STU001",
            "title": "Test Study",
            "start_date": datetime.date(2024, 12, 31),
            "end_date": datetime.date(2024, 1, 1),
        }
        errors = validate(data, "study", version="1.1")
        assert any("date" in e.message.lower() for e in errors)

    def test_validate_returns_all_errors(self) -> None:
        """All validation errors are returned."""
        data = {
            "unique_id": "invalid id with spaces",
            # missing title
        }
        errors = validate(data, "investigation", version="1.1")
        assert len(errors) >= 2

    def test_validate_model_instance(self) -> None:
        """Validate a Pydantic model instance directly."""
        from metaseed.models import get_model

        Investigation = get_model("Investigation")
        Person = get_model("Person")
        Study = get_model("Study")
        inv = Investigation(
            unique_id="INV001",
            title="Test",
            contacts=[Person(name="Test Contact")],
            studies=[
                Study(unique_id="STU001", title="Test Study", investigation_id="INV001")
            ],
        )

        # Entity type is auto-detected from model class name
        errors = validate(inv)
        assert len(errors) == 0

    def test_validate_cascading(self) -> None:
        """Cascading validation checks nested entities."""
        from metaseed.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")
        Person = get_model("Person")

        inv = Investigation(
            unique_id="INV001",
            title="Test",
            contacts=[Person(name="Test Contact")],
            studies=[
                Study(
                    unique_id="STU001",
                    title="Study",
                    investigation_id="INV001",
                    start_date=datetime.date(2024, 12, 31),
                    end_date=datetime.date(2024, 1, 1),  # End before start
                ),
            ],
        )

        errors = validate(inv, cascade=True)

        # Should find date range error in nested study
        assert len(errors) >= 1
        # Check that errors have path prefixes for nested entities
        assert any("studies[0]" in e.field for e in errors)

    def test_validate_no_cascade(self) -> None:
        """Without cascade, only validates the top-level entity."""
        from metaseed.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")
        Person = get_model("Person")

        inv = Investigation(
            unique_id="INV001",
            title="Test",
            contacts=[Person(name="Test Contact")],
            studies=[
                Study(
                    unique_id="STU001",
                    title="Study",
                    investigation_id="INV001",
                    start_date=datetime.date(2024, 12, 31),
                    end_date=datetime.date(2024, 1, 1),  # Invalid dates
                ),
            ],
        )

        # Without cascade, should only validate Investigation (which is valid)
        errors = validate(inv, cascade=False)
        assert len(errors) == 0  # Investigation itself is valid

    def test_validate_cascade_list_of_primitive(self) -> None:
        """Cascading over a list field whose items are a primitive type.

        ``observation_unit_level_hierarchy`` has ``items: string``; resolving
        it as an entity raises SpecLoadError, which the nested traversal must
        swallow rather than let escape the public ``validate`` function.
        """
        data = {
            "unique_id": "STU001",
            "title": "Study",
            "observation_unit_level_hierarchy": ["plot", "plant"],
        }

        errors = validate(
            data, entity="study", version="1.2", profile="miappe", cascade=True
        )

        # The primitive-list field must not be treated as a nested entity.
        assert isinstance(errors, list)


class TestExplicitRuleTypes:
    """Tests for explicit rule type handling in engine."""

    def test_explicit_conditional_type(self) -> None:
        """Explicit conditional type creates ConditionalRule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="conditional",
            condition="a OR b",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, ConditionalRule)
        assert rule.condition == "a OR b"

    def test_explicit_date_range_type(self) -> None:
        """Explicit date_range type creates DateRangeRule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="date_range",
            start_field="start_date",
            end_field="end_date",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, DateRangeRule)
        assert rule.start_field == "start_date"
        assert rule.end_field == "end_date"

    def test_date_range_from_condition(self) -> None:
        """date_range type can parse fields from condition."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="date_range",
            condition="end_date >= start_date",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, DateRangeRule)
        assert rule.start_field == "start_date"
        assert rule.end_field == "end_date"

    def test_explicit_coordinate_pair_type(self) -> None:
        """Explicit coordinate_pair type creates CoordinatePairRule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="coordinate_pair",
            lat_field="site_lat",
            lon_field="site_lon",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, CoordinatePairRule)
        assert rule.lat_field == "site_lat"
        assert rule.lon_field == "site_lon"

    def test_coordinate_pair_defaults(self) -> None:
        """coordinate_pair type uses default field names."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="coordinate_pair",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, CoordinatePairRule)
        assert rule.lat_field == "latitude"
        assert rule.lon_field == "longitude"

    def test_condition_coordinate_pair_uses_actual_field_names(self) -> None:
        """A condition-inferred coordinate rule targets the real lat/lon fields.

        Previously only the ``biological_material_`` prefix was special-cased and
        every other entity fell back to a bare ``latitude``/``longitude`` that does
        not exist, so the rule silently validated the wrong fields.
        """
        from metaseed.validators.engine import _infer_rule_type

        spec = ValidationRuleSpec(
            name="coord",
            condition="material_source_latitude AND material_source_longitude",
            message="m",
        )
        rule = _infer_rule_type(spec)
        assert isinstance(rule, CoordinatePairRule)
        assert rule.lat_field == "material_source_latitude"
        assert rule.lon_field == "material_source_longitude"

    def test_explicit_cardinality_type(self) -> None:
        """Explicit cardinality type creates ListCardinalityRule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="cardinality",
            field="samples",
            min_items=1,
            max_items=10,
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, ListCardinalityRule)
        assert rule.field == "samples"
        assert rule.min_items == 1
        assert rule.max_items == 10

    def test_explicit_uniqueness_type_builds_no_engine_rule(self) -> None:
        """A uniqueness rule spans records, so no engine rule is built for it.

        It is enforced over the whole tree by DatasetValidator; an engine rule
        would see one record and could never fire.
        """
        spec = ValidationRuleSpec(
            name="test_rule",
            type="uniqueness",
            field="identifier",
            unique_within="parent",
        )
        assert _create_rule_from_spec(spec) is None

    def test_explicit_reference_type_builds_no_engine_rule(self) -> None:
        """A reference rule needs dataset-wide ids, so no engine rule is built."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="reference",
            field="protocol_id",
            reference="Protocol.identifier",
        )
        assert _create_rule_from_spec(spec) is None

    def test_custom_message_passed_to_rule(self) -> None:
        """Custom message is passed to created rule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="conditional",
            condition="a OR b",
            message="Please provide either A or B",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, ConditionalRule)
        assert rule.custom_message == "Please provide either A or B"

    def test_unknown_explicit_type_raises(self) -> None:
        """A mistyped explicit rule type fails loudly instead of no-opping.

        Without this, ``type: unique`` (a typo for ``uniqueness``) would be
        silently dropped and the rule would never run, so invalid data could
        be reported valid.
        """
        spec = ValidationRuleSpec(
            name="dup_ids",
            type="unique",  # typo for "uniqueness"
            field="unique_id",
            unique_within="parent",
        )
        with pytest.raises(ValueError, match="unknown type 'unique'"):
            _create_rule_from_spec(spec)

    def test_single_entity_engine_omits_reference_rules(self) -> None:
        """A per-entity engine must not carry dead reference-integrity rules.

        BiologicalMaterial declares a Study.unique_id reference rule. At
        single-entity scope there is no set of dataset-wide IDs, so such a rule
        can only no-op or false-positive; it must not be built (reference
        integrity is enforced by DatasetValidator instead).
        """
        from metaseed.validators.engine import create_engine_for_entity

        engine = create_engine_for_entity(
            "BiologicalMaterial", version="1.1", profile="miappe"
        )
        assert not any(rule.name == "entity_reference" for rule in engine.rules)

    def test_missing_profile_raises_spec_load_error(self) -> None:
        """A nonexistent profile is handled via SpecLoadError, not a crash.

        The profile is loaded through the public ``SpecLoader.load_profile``,
        which raises ``SpecLoadError`` when the profile is absent; the builder
        catches it and, with no entity found either, re-raises SpecLoadError
        rather than dereferencing a None spec.
        """
        from metaseed.specs.loader import SpecLoadError
        from metaseed.validators.engine import create_engine_for_entity

        with pytest.raises(SpecLoadError):
            create_engine_for_entity(
                "Investigation", version="1.2", profile="no-such-profile-xyz"
            )


class TestInferredRuleTypes:
    """Tests for backward-compatible rule type inference."""

    def test_inferred_uniqueness_builds_no_engine_rule(self) -> None:
        """An untyped unique_within rule builds nothing here either."""
        spec = ValidationRuleSpec(
            name="test_rule",
            field="identifier",
            unique_within="global",
        )
        assert _create_rule_from_spec(spec) is None

    def test_inferred_reference_builds_no_engine_rule(self) -> None:
        """An untyped reference rule builds nothing here either."""
        spec = ValidationRuleSpec(
            name="test_rule",
            field="study_id",
            reference="Study.identifier",
        )
        assert _create_rule_from_spec(spec) is None

    def test_pattern_rule_skipped(self) -> None:
        """Pattern rules return None (handled by Pydantic)."""
        spec = ValidationRuleSpec(
            name="test_rule",
            field="email",
            pattern="^[a-z]+@[a-z]+\\.[a-z]+$",
        )
        rule = _create_rule_from_spec(spec)
        assert rule is None

    def test_enum_rule_skipped(self) -> None:
        """Enum rules return None (handled by Pydantic)."""
        spec = ValidationRuleSpec(
            name="test_rule",
            field="status",
            enum=["draft", "published"],
        )
        rule = _create_rule_from_spec(spec)
        assert rule is None

    def test_range_rule_skipped(self) -> None:
        """Range rules return None (handled by Pydantic)."""
        spec = ValidationRuleSpec(
            name="test_rule",
            field="latitude",
            minimum=-90,
            maximum=90,
        )
        rule = _create_rule_from_spec(spec)
        assert rule is None


class TestADeclaredPatternWins:
    """MIAPPE's identifier shape must not be imposed on other profiles.

    ``create_engine_for_entity`` added a rule allowing only ``[A-Za-z0-9_-]`` to
    any field named ``identifier`` or ``unique_id``, in any profile, chosen by
    the field's *name*. DiSSCo declares its own pattern for that field — a DOI,
    which contains ``:`` and ``/`` — so the two rules could not both be
    satisfied and no valid DiSSCo specimen could be created while identifier
    validation was on (#246).

    Where a profile states what its identifier looks like, that statement is the
    answer. The default applies only where nothing was stated.
    """

    def test_a_doi_identifier_is_accepted_where_the_profile_declares_it(self) -> None:
        engine = create_engine_for_entity(
            "DigitalSpecimen", version="0.4", profile="dissco"
        )

        errors = engine.validate({"identifier": "https://doi.org/10.22/AB"})

        assert not [e for e in errors if e.field == "identifier"], (
            "the profile's own identifier pattern was overruled by MIAPPE's"
        )

    def test_the_profiles_own_pattern_still_rejects_a_wrong_identifier(self) -> None:
        """Dropping the default must not leave the field unchecked."""
        engine = create_engine_for_entity(
            "DigitalSpecimen", version="0.4", profile="dissco"
        )

        errors = engine.validate({"identifier": "not-a-doi"})

        assert [e for e in errors if e.field == "identifier"], (
            "an identifier that is not a DOI passed a profile that requires one"
        )

    def test_miappe_keeps_its_identifier_rule(self) -> None:
        """The default is still the answer where a profile states nothing."""
        engine = create_engine_for_entity(
            "Investigation", version="1.1", profile="miappe"
        )

        errors = engine.validate({"unique_id": "has spaces"})

        assert [e for e in errors if e.field == "unique_id"]


class TestARangeIsComparedByItsOperands:
    """A numeric range must not be checked by the date validator.

    ``A >= B`` was turned into a ``DateRangeRule`` whatever A and B were, so
    Darwin Core's ``maximumDepthInMeters >= minimumDepthInMeters`` reported
    "not a valid date" for two floats — and those two fields could never both be
    populated (#246). Rules were routed by the shape of the condition; they are
    now routed by what the operands are.
    """

    def test_a_depth_range_accepts_numbers(self) -> None:
        engine = create_engine_for_entity(
            "Location", version="1.0", profile="darwin-core"
        )

        errors = engine.validate(
            {"minimumDepthInMeters": 1.0, "maximumDepthInMeters": 5.0}
        )

        assert not [e for e in errors if "Depth" in (e.field or "")], (
            "a numeric depth range was checked as if it were a date"
        )

    def test_an_inverted_depth_range_is_still_reported(self) -> None:
        """Routing it correctly must not mean not checking it."""
        engine = create_engine_for_entity(
            "Location", version="1.0", profile="darwin-core"
        )

        errors = engine.validate(
            {"minimumDepthInMeters": 9.0, "maximumDepthInMeters": 2.0}
        )

        assert [e for e in errors if "Depth" in (e.field or "")], (
            "a maximum below its minimum passed unreported"
        )

    def test_a_date_range_is_still_a_date_range(self) -> None:
        engine = create_engine_for_entity("Study", version="1.1", profile="miappe")

        assert any(r.name == "date_range" for r in engine.rules), (
            "date ranges must keep being checked as dates"
        )
