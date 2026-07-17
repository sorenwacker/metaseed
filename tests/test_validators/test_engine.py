"""Tests for validation engine."""

import datetime

import pytest

from metaseed.specs.schema import ValidationRuleSpec
from metaseed.validators import validate
from metaseed.validators.engine import (
    ValidationEngine,
    _create_rule_from_spec,
)
from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    EntityReferenceRule,
    ListCardinalityRule,
    RequiredFieldsRule,
    UniquenessRule,
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

    def test_explicit_uniqueness_type(self) -> None:
        """Explicit uniqueness type creates UniquenessRule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            type="uniqueness",
            field="identifier",
            unique_within="parent",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, UniquenessRule)
        assert rule.field == "identifier"
        assert rule.scope == "parent"

    def test_explicit_reference_type(self) -> None:
        """Explicit reference type creates EntityReferenceRule."""
        available_refs = {"Protocol": {"PROT-001", "PROT-002"}}
        spec = ValidationRuleSpec(
            name="test_rule",
            type="reference",
            field="protocol_id",
            reference="Protocol.identifier",
        )
        rule = _create_rule_from_spec(spec, available_refs)
        assert isinstance(rule, EntityReferenceRule)
        assert rule.field == "protocol_id"
        assert rule.reference_id_field == "identifier"
        assert rule.available_ids == {"PROT-001", "PROT-002"}

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


class TestInferredRuleTypes:
    """Tests for backward-compatible rule type inference."""

    def test_infer_uniqueness_from_unique_within(self) -> None:
        """Rule with unique_within creates UniquenessRule."""
        spec = ValidationRuleSpec(
            name="test_rule",
            field="identifier",
            unique_within="global",
        )
        rule = _create_rule_from_spec(spec)
        assert isinstance(rule, UniquenessRule)
        assert rule.scope == "global"

    def test_infer_reference_from_reference_field(self) -> None:
        """Rule with reference creates EntityReferenceRule."""
        available_refs = {"Study": {"STU-001"}}
        spec = ValidationRuleSpec(
            name="test_rule",
            field="study_id",
            reference="Study.identifier",
        )
        rule = _create_rule_from_spec(spec, available_refs)
        assert isinstance(rule, EntityReferenceRule)

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
