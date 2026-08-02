"""Tests for the extraction agent core module."""

import json
from pathlib import Path

import pytest

from metaseed.agent.core import (
    ExtractionContext,
    ValidationIssue,
    parse_file,
)
from metaseed.agent.mapping import ColumnMapping, FieldMapping, suggest_mapping


class TestParseFile:
    """Tests for parse_file function."""

    def test_parse_csv(self, tmp_path: Path) -> None:
        """Parse a CSV file."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,value,description\nfoo,1,A foo\nbar,2,A bar\n")

        content = parse_file(csv_file)

        assert content.format == "csv"
        assert len(content.tables) == 1
        assert content.tables[0].headers == ["name", "value", "description"]
        assert content.tables[0].row_count == 2

    def test_parse_json(self, tmp_path: Path) -> None:
        """Parse a JSON file with array of objects."""
        json_file = tmp_path / "test.json"
        json_file.write_text(
            json.dumps([{"name": "foo", "value": 1}, {"name": "bar", "value": 2}])
        )

        content = parse_file(json_file)

        assert content.format == "json"
        assert len(content.tables) == 1
        assert "name" in content.tables[0].headers
        assert "value" in content.tables[0].headers

    def test_parse_unsupported_format(self, tmp_path: Path) -> None:
        """Raise error for unsupported file format."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Some text content")

        with pytest.raises(ValueError, match="No parser found"):
            parse_file(txt_file)


class TestSuggestMapping:
    """Tests for suggest_mapping function."""

    def test_exact_match(self) -> None:
        """Exact column name matches field name."""
        from metaseed.specs.loader import SpecLoader

        loader = SpecLoader(profile="miappe")
        try:
            entity = loader.load_entity("Investigation", version="1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        # Use actual MIAPPE Investigation fields
        columns = ["unique_id", "title", "description"]
        mappings = suggest_mapping(columns, entity)

        # Find mapping for unique_id
        id_mapping = next((m for m in mappings if m.field_name == "unique_id"), None)
        assert id_mapping is not None
        assert id_mapping.source_column == "unique_id"
        assert id_mapping.confidence >= 0.9

    def test_fuzzy_match(self) -> None:
        """Similar column names get matched with lower confidence."""
        from metaseed.specs.loader import SpecLoader

        loader = SpecLoader(profile="miappe")
        try:
            entity = loader.load_entity("Investigation", version="1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        # Use similar but not exact names
        columns = ["inv_title", "inv_description", "id"]
        mappings = suggest_mapping(columns, entity)

        # Should still find some matches
        matched = [m for m in mappings if m.source_column is not None]
        assert len(matched) > 0

    def test_no_match(self) -> None:
        """Unrelated column names don't match."""
        from metaseed.specs.loader import SpecLoader

        loader = SpecLoader(profile="miappe")
        try:
            entity = loader.load_entity("Investigation", version="1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        columns = ["xyz123", "random_col", "unrelated"]
        mappings = suggest_mapping(columns, entity, threshold=0.8)

        # With high threshold, shouldn't match random columns
        matched = [
            m for m in mappings if m.source_column is not None and m.confidence >= 0.8
        ]
        assert len(matched) == 0


class TestExtractionContext:
    """Tests for ExtractionContext class."""

    def test_create_from_profile(self) -> None:
        """Create context from profile name and version."""
        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
            assert ctx.profile.name.lower() == "miappe"
            assert ctx.profile.version == "1.1"
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

    def test_add_source(self, tmp_path: Path) -> None:
        """Add a source file to the context."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("unique_id,title\nINV-001,My Investigation\n")

        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        content = ctx.add_source(csv_file)

        assert len(ctx.sources) == 1
        assert content.format == "csv"

    def test_suggest_mapping(self, tmp_path: Path) -> None:
        """Get mapping suggestions for a source."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("unique_id,title,description\nINV-001,Test,A test\n")

        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        ctx.add_source(csv_file)
        mappings = ctx.suggest_mapping(0, "Investigation")

        assert len(mappings) > 0
        # unique_id should match
        id_mapping = next((m for m in mappings if m.field_name == "unique_id"), None)
        assert id_mapping is not None
        assert id_mapping.source_column == "unique_id"

    def test_extract_entities(self, tmp_path: Path) -> None:
        """Extract entities using a mapping."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "unique_id,title\nINV-001,My Investigation\nINV-002,Another\n"
        )

        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        ctx.add_source(csv_file)

        # Create explicit mapping using actual MIAPPE field names
        mapping = ColumnMapping(
            entity_name="Investigation",
            fields=[
                FieldMapping(
                    field_name="unique_id", source_column="unique_id", confidence=1.0
                ),
                FieldMapping(field_name="title", source_column="title", confidence=1.0),
            ],
        )
        ctx.set_mapping("Investigation", mapping)

        result = ctx.extract_entities(0, "Investigation")

        assert result.entity == "Investigation"
        assert len(result.instances) == 2
        assert result.instances[0]["unique_id"] == "INV-001"
        assert result.instances[1]["unique_id"] == "INV-002"

    def test_extract_entities_skips_empty_optional_fields(self, tmp_path: Path) -> None:
        """Optional fields with empty/missing values are not written as null keys."""
        csv_file = tmp_path / "data.csv"
        # 'description' is an optional MIAPPE Investigation field; leave it blank.
        csv_file.write_text("unique_id,title,description\nINV-001,My Investigation,\n")

        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        ctx.add_source(csv_file)
        mapping = ColumnMapping(
            entity_name="Investigation",
            fields=[
                FieldMapping(field_name="unique_id", source_column="unique_id"),
                FieldMapping(field_name="title", source_column="title"),
                FieldMapping(field_name="description", source_column="description"),
            ],
        )
        ctx.set_mapping("Investigation", mapping)

        result = ctx.extract_entities(0, "Investigation")

        assert len(result.instances) == 1
        instance = result.instances[0]
        # The empty optional field must be skipped entirely, not stored as None.
        assert "description" not in instance
        assert instance["unique_id"] == "INV-001"

    def test_validate_instance(self) -> None:
        """Validate an extracted instance."""
        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        # Valid instance using actual MIAPPE field names
        valid_data = {"unique_id": "INV-001", "title": "Test Investigation"}
        errors = ctx.validate_instance(valid_data, "Investigation")
        # unique_id and title are required fields, so with both provided there should be no errors
        assert not any(e.field in ("unique_id", "title") for e in errors), (
            f"Expected no errors for unique_id/title, got: {errors}"
        )

        # Instance missing required fields
        empty_data: dict = {}
        errors = ctx.validate_instance(empty_data, "Investigation")
        # Should have errors for missing required fields (unique_id is always required)
        assert any(e.field == "unique_id" for e in errors), (
            f"Expected error for missing 'unique_id' field, got errors: {errors}"
        )

        # A required field present with a null value is as absent as a missing key.
        null_data = {"unique_id": None, "title": "Test"}
        errors = ctx.validate_instance(null_data, "Investigation")
        assert any(e.field == "unique_id" for e in errors), (
            f"Expected error for required 'unique_id' set to None, got: {errors}"
        )

    def test_export_yaml(self, tmp_path: Path) -> None:
        """Export extracted data to YAML."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("unique_id,title\nINV-001,Test\n")

        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        ctx.add_source(csv_file)
        mapping = ColumnMapping(
            entity_name="Investigation",
            fields=[
                FieldMapping(field_name="unique_id", source_column="unique_id"),
                FieldMapping(field_name="title", source_column="title"),
            ],
        )
        ctx.set_mapping("Investigation", mapping)
        ctx.extract_entities(0, "Investigation")

        yaml_output = ctx.export_yaml("Investigation")

        assert "Investigation:" in yaml_output
        assert "INV-001" in yaml_output

    def test_export_json(self, tmp_path: Path) -> None:
        """Export extracted data to JSON."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("unique_id,title\nINV-001,Test\n")

        try:
            ctx = ExtractionContext.from_profile("miappe", "1.1")
        except Exception:
            pytest.skip("MIAPPE 1.1 profile not available")

        ctx.add_source(csv_file)
        mapping = ColumnMapping(
            entity_name="Investigation",
            fields=[
                FieldMapping(field_name="unique_id", source_column="unique_id"),
                FieldMapping(field_name="title", source_column="title"),
            ],
        )
        ctx.set_mapping("Investigation", mapping)
        ctx.extract_entities(0, "Investigation")

        json_output = ctx.export_json("Investigation")
        data = json.loads(json_output)

        assert "Investigation" in data
        assert len(data["Investigation"]) == 1
        assert data["Investigation"][0]["unique_id"] == "INV-001"


class TestColumnMapping:
    """Tests for ColumnMapping class."""

    def test_get_field_mapping(self) -> None:
        """Get a specific field mapping."""
        mapping = ColumnMapping(
            entity_name="Test",
            fields=[
                FieldMapping(field_name="foo", source_column="col1"),
                FieldMapping(field_name="bar", source_column="col2"),
            ],
        )

        foo = mapping.get_field_mapping("foo")
        assert foo is not None
        assert foo.source_column == "col1"

        missing = mapping.get_field_mapping("nonexistent")
        assert missing is None

    def test_set_field_mapping(self) -> None:
        """Set or update a field mapping."""
        mapping = ColumnMapping(entity_name="Test", fields=[])

        # Add new mapping
        mapping.set_field_mapping("foo", "col1", confidence=0.9)
        assert len(mapping.fields) == 1
        assert mapping.fields[0].source_column == "col1"

        # Update existing
        mapping.set_field_mapping("foo", "col2", confidence=1.0)
        assert len(mapping.fields) == 1
        assert mapping.fields[0].source_column == "col2"
        assert mapping.fields[0].confidence == 1.0


class TestProfileRulesOnExtractedRecords:
    """The extracted-data path runs the profile's validation rules."""

    @staticmethod
    def _context() -> ExtractionContext:
        """An extraction context for MIAPPE 1.2."""
        return ExtractionContext.from_profile("miappe", "1.2")

    def test_record_violating_a_profile_rule_is_reported(self) -> None:
        # MIAPPE declares observed_variable_trait_required:
        # "trait OR trait_accession_number". Neither is a required field, so
        # only the rule can catch this record.
        ctx = self._context()

        errors = ctx.validate_instance(
            {"unique_id": "OV-001", "variable_name": "Plant height"},
            "ObservedVariable",
        )

        assert "observed_variable_trait_required" in {e.rule for e in errors}

    def test_record_satisfying_the_rule_is_not_reported(self) -> None:
        ctx = self._context()

        errors = ctx.validate_instance(
            {
                "unique_id": "OV-001",
                "variable_name": "Plant height",
                "trait": "plant height",
                "method": "ruler",
                "scale": "cm",
            },
            "ObservedVariable",
        )

        assert [e for e in errors if e.rule == "observed_variable_trait_required"] == []

    def test_issue_from_a_field_check_carries_no_rule_name(self) -> None:
        ctx = self._context()

        errors = ctx.validate_instance({}, "ObservedVariable")

        missing = [e for e in errors if e.field == "unique_id"]
        assert missing and missing[0].rule is None

    def test_absent_child_collections_do_not_fault_a_row(self) -> None:
        # investigation_has_studies is a cardinality rule over a child
        # collection, which an extracted row never carries.
        ctx = self._context()

        errors = ctx.validate_instance(
            {"unique_id": "INV-001", "title": "Test"}, "Investigation"
        )

        assert errors == []


class TestValidationIssue:
    """Tests for ValidationIssue class."""

    def test_create_validation_error(self) -> None:
        """Create a validation error."""
        error = ValidationIssue(
            field="unique_id",
            message="Field is required",
            value=None,
        )

        assert error.field == "unique_id"
        assert "required" in error.message
        assert error.value is None
