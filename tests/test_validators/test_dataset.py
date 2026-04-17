"""Tests for dataset validation."""

from pathlib import Path

from metaseed.validators.dataset import (
    DatasetValidationResult,
    DatasetValidator,
    IdRegistry,
)


class TestIdRegistry:
    """Tests for IdRegistry."""

    def test_register_and_exists(self) -> None:
        """Register an ID and check existence."""
        registry = IdRegistry()
        registry.register("study", "STU001")

        assert registry.exists("study", "STU001")
        assert not registry.exists("study", "STU002")
        assert not registry.exists("investigation", "STU001")

    def test_register_multiple_types(self) -> None:
        """Register IDs of different types."""
        registry = IdRegistry()
        registry.register("study", "STU001")
        registry.register("observation_unit", "OBS001")

        assert registry.exists("study", "STU001")
        assert registry.exists("observation_unit", "OBS001")
        assert not registry.exists("study", "OBS001")

    def test_get_ids(self) -> None:
        """Get all IDs for a type."""
        registry = IdRegistry()
        registry.register("study", "STU001")
        registry.register("study", "STU002")

        ids = registry.get_ids("study")
        assert ids == {"STU001", "STU002"}

    def test_get_ids_empty(self) -> None:
        """Get IDs for non-existent type returns empty set."""
        registry = IdRegistry()
        assert registry.get_ids("nonexistent") == set()

    def test_get_all_types(self) -> None:
        """Get all registered entity types."""
        registry = IdRegistry()
        registry.register("study", "STU001")
        registry.register("observation_unit", "OBS001")

        types = registry.get_all_types()
        assert set(types) == {"study", "observation_unit"}


class TestDatasetValidationResult:
    """Tests for DatasetValidationResult."""

    def test_is_valid_no_errors(self) -> None:
        """Result with no errors is valid."""
        result = DatasetValidationResult()
        assert result.is_valid

    def test_is_valid_with_errors(self) -> None:
        """Result with errors is not valid."""
        from metaseed.validators.base import ValidationError

        result = DatasetValidationResult()
        result.errors.append(ValidationError(field="test", message="error", rule="test_rule"))
        assert not result.is_valid

    def test_is_valid_with_warnings_only(self) -> None:
        """Result with only warnings is still valid."""
        from metaseed.validators.base import ValidationError

        result = DatasetValidationResult()
        result.warnings.append(ValidationError(field="test", message="warning", rule="test_rule"))
        assert result.is_valid

    def test_merge(self) -> None:
        """Merge two results."""
        from metaseed.validators.base import ValidationError

        result1 = DatasetValidationResult()
        result1.errors.append(ValidationError(field="a", message="error1", rule="rule1"))
        result1.entity_counts["study"] = 2
        result1.files_checked.append(Path("file1.yaml"))

        result2 = DatasetValidationResult()
        result2.errors.append(ValidationError(field="b", message="error2", rule="rule2"))
        result2.entity_counts["study"] = 1
        result2.entity_counts["investigation"] = 1
        result2.files_checked.append(Path("file2.yaml"))

        result1.merge(result2)

        assert len(result1.errors) == 2
        assert result1.entity_counts["study"] == 3
        assert result1.entity_counts["investigation"] == 1
        assert len(result1.files_checked) == 2


class TestDatasetValidator:
    """Tests for DatasetValidator."""

    def test_init_default_profile(self) -> None:
        """Initialize with default profile."""
        validator = DatasetValidator()
        assert validator.profile == "miappe"

    def test_init_explicit_profile(self) -> None:
        """Initialize with explicit profile."""
        validator = DatasetValidator(profile="miappe", version="1.1")
        assert validator.profile == "miappe"
        assert validator.version == "1.1"

    def test_validate_file_valid(self, tmp_path: Path) -> None:
        """Validate a valid file."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    title: Test Study
    investigation_id: INV001
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        validator = DatasetValidator()
        result = validator.validate_file(file_path)

        assert result.is_valid
        assert file_path in result.files_checked

    def test_validate_file_missing_required(self, tmp_path: Path) -> None:
        """Validate file missing required fields."""
        content = """
unique_id: INV001
# missing title
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        validator = DatasetValidator()
        result = validator.validate_file(file_path)

        assert not result.is_valid
        assert any("title" in e.field or "title" in e.message.lower() for e in result.errors)

    def test_validate_file_invalid_yaml(self, tmp_path: Path) -> None:
        """Validate file with invalid YAML syntax."""
        content = """
unique_id: INV001
  bad_indent: invalid
"""
        file_path = tmp_path / "invalid.yaml"
        file_path.write_text(content)

        validator = DatasetValidator()
        result = validator.validate_file(file_path)

        assert not result.is_valid
        assert any("yaml" in e.message.lower() for e in result.errors)

    def test_validate_file_nonexistent(self) -> None:
        """Validate nonexistent file."""
        validator = DatasetValidator()
        result = validator.validate_file(Path("/nonexistent/file.yaml"))

        assert not result.is_valid
        assert len(result.errors) == 1

    def test_validate_directory_valid(self, tmp_path: Path) -> None:
        """Validate a directory with valid files."""
        inv_content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
    start_date: "2024-01-01"
"""
        (tmp_path / "investigation.yaml").write_text(inv_content)

        validator = DatasetValidator()
        result = validator.validate_directory(tmp_path)

        assert result.is_valid
        assert len(result.files_checked) == 1

    def test_validate_directory_empty(self, tmp_path: Path) -> None:
        """Validate empty directory."""
        validator = DatasetValidator()
        result = validator.validate_directory(tmp_path)

        assert result.is_valid  # No errors, just warning
        assert len(result.warnings) == 1
        assert "no yaml" in result.warnings[0].message.lower()

    def test_validate_directory_multiple_files(self, tmp_path: Path) -> None:
        """Validate directory with multiple files."""
        inv_content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies: []
"""
        study_content = """
unique_id: STU001
title: Test Study
investigation_id: INV001
observation_units: []
"""
        (tmp_path / "investigation.yaml").write_text(inv_content)
        (tmp_path / "study.yaml").write_text(study_content)

        validator = DatasetValidator()
        result = validator.validate_directory(tmp_path)

        assert len(result.files_checked) == 2

    def test_entity_counts(self, tmp_path: Path) -> None:
        """Check entity counting."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    title: Study 1
    investigation_id: INV001
  - unique_id: STU002
    title: Study 2
    investigation_id: INV001
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        validator = DatasetValidator()
        result = validator.validate_file(file_path)

        assert result.entity_counts.get("investigation", 0) == 1
        assert result.entity_counts.get("study", 0) == 2


class TestReferenceIntegrity:
    """Tests for reference integrity checking."""

    def test_collect_ids(self, tmp_path: Path) -> None:
        """IDs are collected from nested entities."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    title: Study 1
    investigation_id: INV001
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        validator = DatasetValidator()
        validator.validate_file(file_path)

        # After validation, registry should have both IDs
        assert validator._registry.exists("investigation", "INV001")
        assert validator._registry.exists("study", "STU001")
