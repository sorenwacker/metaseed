"""Tests for validation rules."""

import datetime

from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
    ValidationError,
)


class TestDateRangeRule:
    """Tests for DateRangeRule."""

    def test_valid_date_range(self) -> None:
        """Valid date range passes."""
        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": datetime.date(2024, 1, 1),
            "end_date": datetime.date(2024, 12, 31),
        }
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_same_dates_valid(self) -> None:
        """Same start and end dates are valid."""
        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": datetime.date(2024, 6, 15),
            "end_date": datetime.date(2024, 6, 15),
        }
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_invalid_date_range(self) -> None:
        """End before start returns error."""
        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": datetime.date(2024, 12, 31),
            "end_date": datetime.date(2024, 1, 1),
        }
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "end_date" in errors[0].field or "date" in errors[0].message.lower()

    def test_missing_dates_skipped(self) -> None:
        """Missing dates are skipped (no error)."""
        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {"start_date": datetime.date(2024, 1, 1)}  # No end_date
        errors = rule.validate(data)
        assert len(errors) == 0


class TestRequiredFieldsRule:
    """Tests for RequiredFieldsRule."""

    def test_all_required_present(self) -> None:
        """All required fields present passes."""
        rule = RequiredFieldsRule(fields=["name", "id"])
        data = {"name": "Test", "id": "001"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_missing_required_field(self) -> None:
        """Missing required field returns error."""
        rule = RequiredFieldsRule(fields=["name", "id"])
        data = {"name": "Test"}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "id" in errors[0].field

    def test_empty_string_invalid(self) -> None:
        """Empty string is treated as missing."""
        rule = RequiredFieldsRule(fields=["name"])
        data = {"name": ""}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_none_value_invalid(self) -> None:
        """None value is treated as missing."""
        rule = RequiredFieldsRule(fields=["name"])
        data = {"name": None}
        errors = rule.validate(data)
        assert len(errors) == 1


class TestUniqueIdPatternRule:
    """Tests for UniqueIdPatternRule."""

    def test_valid_id(self) -> None:
        """Valid ID passes."""
        rule = UniqueIdPatternRule(field="unique_id")
        data = {"unique_id": "INV-001_test"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_invalid_id_with_spaces(self) -> None:
        """ID with spaces returns error."""
        rule = UniqueIdPatternRule(field="unique_id")
        data = {"unique_id": "INV 001"}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "unique_id" in errors[0].field

    def test_invalid_id_with_special_chars(self) -> None:
        """ID with invalid special characters returns error."""
        rule = UniqueIdPatternRule(field="unique_id")
        data = {"unique_id": "INV@001#"}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_missing_id_skipped(self) -> None:
        """Missing ID field is skipped."""
        rule = UniqueIdPatternRule(field="unique_id")
        data = {}
        errors = rule.validate(data)
        assert len(errors) == 0


class TestEntityReferenceRule:
    """Tests for EntityReferenceRule cross-reference validation."""

    def test_valid_single_reference(self) -> None:
        """Valid entity reference passes."""
        from metaseed.validators.rules import EntityReferenceRule

        # Available entities by their unique_id
        available_locations = {"LOC-001", "LOC-002"}

        rule = EntityReferenceRule(
            field="geographic_location",
            reference_id_field="unique_id",
            available_ids=available_locations,
        )
        data = {"geographic_location": {"unique_id": "LOC-001", "name": "Field A"}}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_invalid_reference(self) -> None:
        """Invalid entity reference returns error."""
        from metaseed.validators.rules import EntityReferenceRule

        available_locations = {"LOC-001", "LOC-002"}

        rule = EntityReferenceRule(
            field="geographic_location",
            reference_id_field="unique_id",
            available_ids=available_locations,
        )
        data = {"geographic_location": {"unique_id": "LOC-INVALID", "name": "Unknown"}}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "LOC-INVALID" in errors[0].message

    def test_missing_reference_skipped(self) -> None:
        """Missing reference field is skipped."""
        from metaseed.validators.rules import EntityReferenceRule

        rule = EntityReferenceRule(
            field="geographic_location",
            reference_id_field="unique_id",
            available_ids={"LOC-001"},
        )
        data = {}  # No geographic_location
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_none_reference_skipped(self) -> None:
        """None reference is skipped."""
        from metaseed.validators.rules import EntityReferenceRule

        rule = EntityReferenceRule(
            field="geographic_location",
            reference_id_field="unique_id",
            available_ids={"LOC-001"},
        )
        data = {"geographic_location": None}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_list_references_all_valid(self) -> None:
        """All valid list references pass."""
        from metaseed.validators.rules import EntityReferenceRule

        available_sources = {"SRC-001", "SRC-002", "SRC-003"}

        rule = EntityReferenceRule(
            field="derives_from",
            reference_id_field="name",
            available_ids=available_sources,
            is_list=True,
        )
        data = {"derives_from": [{"name": "SRC-001"}, {"name": "SRC-002"}]}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_list_references_with_invalid(self) -> None:
        """Invalid reference in list returns error."""
        from metaseed.validators.rules import EntityReferenceRule

        available_sources = {"SRC-001", "SRC-002"}

        rule = EntityReferenceRule(
            field="derives_from",
            reference_id_field="name",
            available_ids=available_sources,
            is_list=True,
        )
        data = {"derives_from": [{"name": "SRC-001"}, {"name": "SRC-INVALID"}]}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "SRC-INVALID" in errors[0].message


class TestListCardinalityRule:
    """Tests for ListCardinalityRule."""

    def test_min_items_satisfied(self) -> None:
        """List meeting min_items passes."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": [{"name": "S1"}]}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_min_items_violated(self) -> None:
        """Empty list violates min_items."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": []}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "at least 1" in errors[0].message

    def test_min_items_none_treated_as_empty(self) -> None:
        """None field treated as empty list for min_items."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": None}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_max_items_satisfied(self) -> None:
        """List within max_items passes."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", max_items=2)
        data = {"samples": [{"name": "S1"}, {"name": "S2"}]}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_max_items_violated(self) -> None:
        """List exceeding max_items fails."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", max_items=2)
        data = {"samples": [{"name": "S1"}, {"name": "S2"}, {"name": "S3"}]}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "at most 2" in errors[0].message


class TestConditionalRule:
    """Tests for ConditionalRule."""

    def test_or_both_present(self) -> None:
        """OR condition with both fields present passes."""
        rule = ConditionalRule(condition="name OR email")
        data = {"name": "John", "email": "john@test.com"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_or_one_present(self) -> None:
        """OR condition with one field present passes."""
        rule = ConditionalRule(condition="name OR email")
        data = {"name": "John"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_or_none_present(self) -> None:
        """OR condition with no fields present returns error."""
        rule = ConditionalRule(condition="name OR email")
        data = {}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_and_both_present(self) -> None:
        """AND condition with both fields present passes."""
        rule = ConditionalRule(condition="latitude AND longitude")
        data = {"latitude": 45.0, "longitude": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_and_one_missing(self) -> None:
        """AND condition with one field missing returns error."""
        rule = ConditionalRule(condition="latitude AND longitude")
        data = {"latitude": 45.0}
        errors = rule.validate(data)
        assert len(errors) == 1


class TestCoordinatePairRule:
    """Tests for CoordinatePairRule."""

    def test_both_coordinates_present(self) -> None:
        """Both latitude and longitude present passes."""
        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 45.0, "longitude": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_neither_coordinate_present(self) -> None:
        """Neither coordinate present passes."""
        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_only_latitude(self) -> None:
        """Only latitude present returns error."""
        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 45.0}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "longitude" in errors[0].message

    def test_only_longitude(self) -> None:
        """Only longitude present returns error."""
        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {"longitude": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "latitude" in errors[0].message


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_error_creation(self) -> None:
        """ValidationError can be created with all fields."""
        error = ValidationError(
            field="name",
            message="Name is required",
            rule="required",
        )
        assert error.field == "name"
        assert error.message == "Name is required"
        assert error.rule == "required"

    def test_error_str(self) -> None:
        """ValidationError has readable string representation."""
        error = ValidationError(
            field="name",
            message="Name is required",
            rule="required",
        )
        s = str(error)
        assert "name" in s
        assert "required" in s.lower()
