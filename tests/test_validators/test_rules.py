"""Tests for validation rules."""

import datetime
import time

import regex

from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    PatternRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
    ValidationError,
)


class TestPatternReDoS:
    """User-supplied patterns must not hang validation (ReDoS).

    ``(a+)+$`` against a non-matching input backtracks catastrophically under the
    stdlib ``re`` engine -- the original code hung for minutes on ~35 characters.
    These assert the bounded behaviour: matching runs on the ``regex`` engine with
    a per-match timeout, so a pathological pattern returns a validation error
    quickly instead of blocking.
    """

    _EVIL = r"(a+)+$"
    _BAD_INPUT = "a" * 60 + "!"

    def test_pattern_rule_does_not_hang(self) -> None:
        rule = PatternRule(field="x", pattern=self._EVIL)
        start = time.time()
        errors = rule.validate({"x": self._BAD_INPUT})
        assert time.time() - start < 2.0
        assert errors  # non-matching input fails closed

    def test_unique_id_pattern_rule_does_not_hang(self) -> None:
        rule = UniqueIdPatternRule(field="x", pattern=self._EVIL)
        start = time.time()
        errors = rule.validate({"x": self._BAD_INPUT})
        assert time.time() - start < 2.0
        assert errors

    def test_patterns_compile_on_the_regex_engine_not_stdlib_re(self) -> None:
        # The regex engine (not stdlib re) is what makes the timeout possible.
        assert isinstance(PatternRule(field="x", pattern="^a+$").pattern, regex.Pattern)
        assert isinstance(UniqueIdPatternRule(field="x").pattern, regex.Pattern)

    def test_normal_patterns_still_validate(self) -> None:
        rule = PatternRule(field="x", pattern=r"^[A-Za-z0-9_-]+$")
        assert rule.validate({"x": "ok_id-1"}) == []
        assert rule.validate({"x": "bad!value"})


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

    def test_malformed_start_date_reported_not_raised(self) -> None:
        """A malformed start date is reported as a validation error, not raised.

        The engine runs against raw, un-coerced YAML data, so a bad date string
        must surface as a validation error rather than crash the run.
        """
        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": "not-a-date",
            "end_date": "2024-12-31",
        }
        errors = rule.validate(data)
        assert len(errors) == 1
        assert errors[0].field == "start_date"
        assert errors[0].rule == "date_range"

    def test_malformed_end_date_reported_not_raised(self) -> None:
        """A malformed end date is reported as a validation error, not raised."""
        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": "2024-01-01",
            "end_date": "invalid-date-format",
        }
        errors = rule.validate(data)
        assert len(errors) == 1
        assert errors[0].field == "end_date"
        assert errors[0].rule == "date_range"


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

    def test_empty_list_invalid(self) -> None:
        """Empty list is treated as missing, consistent with has_value."""
        rule = RequiredFieldsRule(fields=["items"])
        data = {"items": []}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_zero_value_is_valid(self) -> None:
        """Zero integer is treated as valid (not missing).

        The rule only checks for None or empty string "", so 0 passes.
        This documents that numeric zero is a legitimate value.
        """
        rule = RequiredFieldsRule(fields=["count"])
        data = {"count": 0}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_false_value_is_valid(self) -> None:
        """Boolean False is treated as valid (not missing).

        The rule only checks for None or empty string "", so False passes.
        This documents that False is a legitimate boolean value.
        """
        rule = RequiredFieldsRule(fields=["enabled"])
        data = {"enabled": False}
        errors = rule.validate(data)
        assert len(errors) == 0


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

    def test_integer_id_returns_type_error(self) -> None:
        """Integer ID returns type error.

        UniqueIdPatternRule expects string values. Non-string types return
        an error indicating the field must be a string.
        """
        rule = UniqueIdPatternRule(field="unique_id")
        data = {"unique_id": 12345}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "must be a string" in errors[0].message

    def test_none_id_skipped(self) -> None:
        """None ID is skipped (same as missing).

        When the value is explicitly None, the rule skips validation
        since RequiredFieldsRule should handle None checks.
        """
        rule = UniqueIdPatternRule(field="unique_id")
        data = {"unique_id": None}
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

    def test_non_list_input_skipped(self) -> None:
        """Non-list input is silently skipped.

        When the field contains a non-list value (e.g., string, dict, int),
        the rule returns no errors. This is because non-list values should
        be caught by schema validation, not cardinality rules.
        """
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        # String instead of list
        data = {"samples": "not-a-list"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_dict_input_skipped(self) -> None:
        """Dict input is silently skipped."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": {"name": "S1"}}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_integer_input_skipped(self) -> None:
        """Integer input is silently skipped."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": 42}
        errors = rule.validate(data)
        assert len(errors) == 0


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


class TestUniquenessRule:
    """Tests for UniquenessRule."""

    def test_first_value_passes(self) -> None:
        """First unique value passes."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(field="identifier", scope="parent")
        data = {"identifier": "ID-001"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_duplicate_value_fails(self) -> None:
        """Duplicate value returns error."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(field="identifier", scope="parent")

        # First value passes
        errors = rule.validate({"identifier": "ID-001"})
        assert len(errors) == 0

        # Same value fails
        errors = rule.validate({"identifier": "ID-001"})
        assert len(errors) == 1
        assert "not unique" in errors[0].message

    def test_different_values_pass(self) -> None:
        """Different values all pass."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(field="identifier", scope="parent")

        for i in range(5):
            errors = rule.validate({"identifier": f"ID-{i:03d}"})
            assert len(errors) == 0

    def test_missing_field_skipped(self) -> None:
        """Missing field is skipped."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(field="identifier", scope="parent")
        errors = rule.validate({})
        assert len(errors) == 0

    def test_none_value_skipped(self) -> None:
        """None value is skipped."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(field="identifier", scope="parent")
        errors = rule.validate({"identifier": None})
        assert len(errors) == 0

    def test_reset_clears_seen_values(self) -> None:
        """Reset allows reuse of values."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(field="identifier", scope="parent")

        # First use
        rule.validate({"identifier": "ID-001"})

        # Reset
        rule.reset()

        # Same value now passes
        errors = rule.validate({"identifier": "ID-001"})
        assert len(errors) == 0

    def test_custom_message(self) -> None:
        """Custom message is used."""
        from metaseed.validators.rules import UniquenessRule

        rule = UniquenessRule(
            field="identifier",
            scope="parent",
            message="Identifier must be unique within the study",
        )

        # Add first value
        rule.validate({"identifier": "ID-001"})

        # Duplicate should use custom message
        errors = rule.validate({"identifier": "ID-001"})
        assert len(errors) == 1
        assert errors[0].message == "Identifier must be unique within the study"

    def test_fresh_instance_never_flags_duplicate(self) -> None:
        """Duplicate detection requires reuse; fresh instances each see one value.

        This locks the honest behavior documented on the rule: because the
        validation engine builds a new instance per record, the same value
        passing through separate instances is never reported as a duplicate.
        """
        from metaseed.validators.rules import UniquenessRule

        # A fresh instance per record (as create_engine_for_entity does) never
        # accumulates state, so an identical value passes every time.
        for _ in range(3):
            rule = UniquenessRule(field="identifier", scope="parent")
            errors = rule.validate({"identifier": "ID-001"})
            assert errors == []


class TestCustomMessages:
    """Tests for custom error messages in rules."""

    def test_date_range_custom_message(self) -> None:
        """DateRangeRule uses custom message."""
        rule = DateRangeRule(
            start_field="start",
            end_field="end",
            message="Project end cannot be before project start",
        )
        data = {"start": "2024-12-31", "end": "2024-01-01"}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert errors[0].message == "Project end cannot be before project start"

    def test_conditional_custom_message(self) -> None:
        """ConditionalRule uses custom message."""
        rule = ConditionalRule(
            condition="email OR phone",
            rule_name="contact_info",
            message="Please provide either email or phone number",
        )
        errors = rule.validate({})
        assert len(errors) == 1
        assert errors[0].message == "Please provide either email or phone number"

    def test_coordinate_pair_custom_message(self) -> None:
        """CoordinatePairRule uses custom message."""
        rule = CoordinatePairRule(
            lat_field="lat",
            lon_field="lon",
            message="Latitude and longitude must be provided together",
        )
        errors = rule.validate({"lat": 45.0})
        assert len(errors) == 1
        assert errors[0].message == "Latitude and longitude must be provided together"


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
