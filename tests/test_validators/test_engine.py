"""Tests for validation engine."""

import datetime

from miappe_api.validators import validate
from miappe_api.validators.engine import ValidationEngine
from miappe_api.validators.rules import (
    DateRangeRule,
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
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        inv = Investigation(unique_id="INV001", title="Test")

        # Entity type is auto-detected from model class name
        errors = validate(inv)
        assert len(errors) == 0

    def test_validate_cascading(self) -> None:
        """Cascading validation checks nested entities."""
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")

        inv = Investigation(
            unique_id="INV001",
            title="Test",
            studies=[
                Study(
                    unique_id="STU001",
                    title="Study",
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
        from miappe_api.models import get_model

        Investigation = get_model("Investigation")
        Study = get_model("Study")

        inv = Investigation(
            unique_id="INV001",
            title="Test",
            studies=[
                Study(
                    unique_id="STU001",
                    title="Study",
                    start_date=datetime.date(2024, 12, 31),
                    end_date=datetime.date(2024, 1, 1),  # Invalid dates
                ),
            ],
        )

        # Without cascade, should only validate Investigation (which is valid)
        errors = validate(inv, cascade=False)
        assert len(errors) == 0  # Investigation itself is valid
