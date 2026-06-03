"""Tests for spec loader."""

from pathlib import Path

import pytest

from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import EntitySpec, FieldType


class TestSpecLoader:
    """Tests for SpecLoader class."""

    @pytest.fixture
    def loader(self) -> SpecLoader:
        """Create a spec loader instance."""
        return SpecLoader()

    @pytest.fixture
    def valid_spec_yaml(self, tmp_path: Path) -> Path:
        """Create a valid spec YAML file."""
        content = """
name: Investigation
version: "1.1"
ontology_term: ppeo:investigation
description: A phenotyping project containing one or more studies

fields:
  - name: unique_id
    type: string
    required: true
    description: Unique identifier
    ontology_term: MIAPPE:DM-1
    constraints:
      pattern: "^[A-Za-z0-9_-]+$"

  - name: title
    type: string
    required: true
    description: Human-readable title
    constraints:
      max_length: 255

  - name: description
    type: string
    required: false
    description: Detailed description

  - name: submission_date
    type: date
    required: false
    description: Submission date

  - name: public_release_date
    type: date
    required: false
    description: Public release date

  - name: license
    type: uri
    required: false
    description: License URL

  - name: studies
    type: list
    items: Study
    required: false
    description: List of studies in this investigation
"""
        spec_file = tmp_path / "investigation.yaml"
        spec_file.write_text(content)
        return spec_file

    @pytest.fixture
    def invalid_yaml(self, tmp_path: Path) -> Path:
        """Create an invalid YAML file."""
        content = """
name: Investigation
version: "1.1"
  invalid indentation
fields:
"""
        spec_file = tmp_path / "invalid.yaml"
        spec_file.write_text(content)
        return spec_file

    @pytest.fixture
    def missing_required_fields_yaml(self, tmp_path: Path) -> Path:
        """Create a spec missing required fields."""
        content = """
name: Test
# missing version
description: Test entity
fields: []
"""
        spec_file = tmp_path / "missing.yaml"
        spec_file.write_text(content)
        return spec_file

    @pytest.fixture
    def invalid_field_type_yaml(self, tmp_path: Path) -> Path:
        """Create a spec with invalid field type."""
        content = """
name: Test
version: "1.0"
description: Test entity
fields:
  - name: test_field
    type: invalid_type
    description: Test
"""
        spec_file = tmp_path / "invalid_type.yaml"
        spec_file.write_text(content)
        return spec_file

    def test_load_valid_spec(self, loader: SpecLoader, valid_spec_yaml: Path) -> None:
        """Load a valid spec file."""
        spec = loader.load(valid_spec_yaml)

        assert isinstance(spec, EntitySpec)
        assert spec.name == "Investigation"
        assert spec.version == "1.1"
        assert spec.ontology_term == "ppeo:investigation"
        assert len(spec.fields) == 7

    def test_load_fields_parsed_correctly(
        self, loader: SpecLoader, valid_spec_yaml: Path
    ) -> None:
        """Fields are parsed with correct types and constraints."""
        spec = loader.load(valid_spec_yaml)

        # Check first field (string with pattern)
        unique_id = spec.fields[0]
        assert unique_id.name == "unique_id"
        assert unique_id.type == FieldType.STRING
        assert unique_id.required is True
        assert unique_id.ontology_term == "MIAPPE:DM-1"
        assert unique_id.constraints is not None
        assert unique_id.constraints.pattern == "^[A-Za-z0-9_-]+$"

        # Check title field (string with max_length)
        title = spec.fields[1]
        assert title.name == "title"
        assert title.constraints is not None
        assert title.constraints.max_length == 255

        # Check date field
        submission_date = spec.fields[3]
        assert submission_date.type == FieldType.DATE

        # Check uri field
        license_field = spec.fields[5]
        assert license_field.type == FieldType.URI

        # Check list field
        studies = spec.fields[6]
        assert studies.type == FieldType.LIST
        assert studies.items == "Study"

    def test_invalid_yaml_raises(self, loader: SpecLoader, invalid_yaml: Path) -> None:
        """Invalid YAML raises SpecLoadError."""
        with pytest.raises(SpecLoadError) as exc_info:
            loader.load(invalid_yaml)
        assert (
            "parse" in str(exc_info.value).lower()
            or "yaml" in str(exc_info.value).lower()
        )

    def test_missing_required_raises(
        self, loader: SpecLoader, missing_required_fields_yaml: Path
    ) -> None:
        """Missing required fields raises SpecLoadError."""
        with pytest.raises(SpecLoadError) as exc_info:
            loader.load(missing_required_fields_yaml)
        assert "version" in str(exc_info.value).lower()

    def test_invalid_field_type_raises(
        self, loader: SpecLoader, invalid_field_type_yaml: Path
    ) -> None:
        """Invalid field type raises SpecLoadError."""
        with pytest.raises(SpecLoadError) as exc_info:
            loader.load(invalid_field_type_yaml)
        assert "type" in str(exc_info.value).lower()

    def test_file_not_found_raises(self, loader: SpecLoader, tmp_path: Path) -> None:
        """Missing file raises SpecLoadError."""
        with pytest.raises(SpecLoadError) as exc_info:
            loader.load(tmp_path / "nonexistent.yaml")
        assert "not found" in str(exc_info.value).lower()

    def test_load_from_string(self, loader: SpecLoader) -> None:
        """Load spec from YAML string."""
        yaml_str = """
name: Test
version: "1.0"
description: Test entity
fields:
  - name: id
    type: string
    required: true
    description: ID
"""
        spec = loader.load_from_string(yaml_str)
        assert spec.name == "Test"
        assert spec.version == "1.0"
        assert len(spec.fields) == 1


class TestSpecLoaderVersioned:
    """Tests for loading versioned specs from the package."""

    @pytest.fixture
    def loader(self) -> SpecLoader:
        """Create a spec loader instance."""
        return SpecLoader()

    def test_load_investigation_v1_1(self, loader: SpecLoader) -> None:
        """Load bundled Investigation spec v1.1."""
        spec = loader.load_entity("investigation", version="1.1")

        assert spec.name == "Investigation"
        assert spec.version == "1.1"
        assert len(spec.fields) > 0
        # Check required fields exist
        field_names = [f.name for f in spec.fields]
        assert "unique_id" in field_names
        assert "title" in field_names

    def test_load_nonexistent_entity_raises(self, loader: SpecLoader) -> None:
        """Loading nonexistent entity raises SpecLoadError."""
        with pytest.raises(SpecLoadError) as exc_info:
            loader.load_entity("nonexistent_entity", version="1.1")
        assert "not found" in str(exc_info.value).lower()

    def test_load_nonexistent_version_raises(self, loader: SpecLoader) -> None:
        """Loading nonexistent version raises SpecLoadError."""
        with pytest.raises(SpecLoadError) as exc_info:
            loader.load_entity("investigation", version="99.99")
        assert "not found" in str(exc_info.value).lower()

    def test_list_entities(self, loader: SpecLoader) -> None:
        """List available entities for a version."""
        entities = loader.list_entities(version="1.1")

        # Should include Investigation (case-insensitive check)
        entities_lower = [e.lower() for e in entities]
        assert "investigation" in entities_lower

    def test_list_versions(self, loader: SpecLoader) -> None:
        """List available versions."""
        versions = loader.list_versions()

        assert "1.1" in versions


class TestISAProfile:
    """Tests for loading ISA profile specs."""

    @pytest.fixture
    def isa_loader(self) -> SpecLoader:
        """Create a spec loader for ISA profile."""
        return SpecLoader(profile="isa")

    def test_list_profiles(self, isa_loader: SpecLoader) -> None:
        """List available profiles."""
        profiles = isa_loader.list_profiles()

        assert "isa" in profiles
        assert "miappe" in profiles

    def test_load_isa_version(self, isa_loader: SpecLoader) -> None:
        """Load ISA profile v1.0."""
        versions = isa_loader.list_versions()

        assert "1.0" in versions

    def test_list_isa_entities(self, isa_loader: SpecLoader) -> None:
        """List ISA entities for v1.0."""
        entities = isa_loader.list_entities(version="1.0")

        # ISA should have core entities
        entities_lower = [e.lower() for e in entities]
        assert "investigation" in entities_lower
        assert "study" in entities_lower
        assert "assay" in entities_lower
        assert "person" in entities_lower
        assert "sample" in entities_lower
        assert "source" in entities_lower
        assert "protocol" in entities_lower

    def test_load_isa_investigation(self, isa_loader: SpecLoader) -> None:
        """Load ISA Investigation spec."""
        spec = isa_loader.load_entity("investigation", version="1.0")

        assert spec.name == "Investigation"
        assert spec.version == "1.0"
        field_names = [f.name for f in spec.fields]
        assert "identifier" in field_names
        assert "title" in field_names
        assert "studies" in field_names

    def test_load_isa_study(self, isa_loader: SpecLoader) -> None:
        """Load ISA Study spec."""
        spec = isa_loader.load_entity("study", version="1.0")

        assert spec.name == "Study"
        field_names = [f.name for f in spec.fields]
        assert "identifier" in field_names
        assert "title" in field_names
        assert "assays" in field_names
        assert "protocols" in field_names

    def test_load_isa_assay(self, isa_loader: SpecLoader) -> None:
        """Load ISA Assay spec."""
        spec = isa_loader.load_entity("assay", version="1.0")

        assert spec.name == "Assay"
        field_names = [f.name for f in spec.fields]
        assert "filename" in field_names
        assert "measurement_type" in field_names
        assert "technology_type" in field_names


class TestSpecVersionBackwardCompatibility:
    """Tests for spec_version backward compatibility."""

    @pytest.fixture
    def loader(self) -> SpecLoader:
        """Create a spec loader instance."""
        return SpecLoader()

    def test_existing_profiles_have_default_spec_version(
        self, loader: SpecLoader
    ) -> None:
        """Existing profiles without spec_version get default 0.1."""
        profile = loader.load_profile(version="1.1", profile="miappe")
        assert profile.spec_version == "0.1"

    def test_isa_profile_has_default_spec_version(self, loader: SpecLoader) -> None:
        """ISA profile without spec_version gets default 0.1."""
        profile = loader.load_profile(version="1.0", profile="isa")
        assert profile.spec_version == "0.1"

    def test_profile_with_explicit_spec_version(self, tmp_path: Path) -> None:
        """Profile with explicit spec_version uses that value."""
        content = """
spec_version: "0.2"
name: test-profile
version: "1.0"
ontologies:
  OBI:
    name: Ontology for Biomedical Investigations
    ols_id: obi
entities:
  Sample:
    fields:
      - name: id
        type: string
        required: true
"""
        # Create profile structure
        profile_dir = tmp_path / "test-profile" / "1.0"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.yaml").write_text(content)

        # Create loader pointing to tmp_path
        loader = SpecLoader(profile="test-profile")
        # Override user specs dir to use our tmp_path
        loader._user_specs_dir = tmp_path

        profile = loader.load_profile(version="1.0", profile="test-profile")
        assert profile.spec_version == "0.2"
        assert profile.ontologies is not None
        assert "OBI" in profile.ontologies
        assert profile.ontologies["OBI"].ols_id == "obi"


class TestValidationRuleBackwardCompatibility:
    """Tests for validation rule backward compatibility.

    Old specs without explicit `type` field should still work via inference.
    """

    @pytest.fixture
    def loader(self) -> SpecLoader:
        """Create a spec loader instance."""
        return SpecLoader()

    def test_miappe_validation_rules_load_without_type(
        self, loader: SpecLoader
    ) -> None:
        """MIAPPE validation rules without explicit type load correctly."""
        profile = loader.load_profile(version="1.1", profile="miappe")

        # Find date_range rule (uses condition-based inference)
        # Look for rules with "date_range" in name which use condition
        date_range_rules = [
            r
            for r in profile.validation_rules
            if r.name == "date_range" and r.condition is not None
        ]
        assert len(date_range_rules) > 0

        # These rules should NOT have explicit type (old style)
        for rule in date_range_rules:
            assert rule.type is None  # Old specs don't have explicit type

    def test_old_style_rules_create_engine_rules(self, loader: SpecLoader) -> None:
        """Old-style rules without type create working engine rules."""
        from metaseed.validators.engine import create_engine_for_entity

        # Create engine for Study which has date_range validation
        engine = create_engine_for_entity("Study", version="1.1", profile="miappe")

        # Should have rules including date range
        assert len(engine.rules) > 0

        # Validate with invalid date range
        import datetime

        errors = engine.validate(
            {
                "unique_id": "STU001",
                "title": "Test Study",
                "start_date": datetime.date(2024, 12, 31),
                "end_date": datetime.date(2024, 1, 1),  # Before start
            }
        )

        # Should catch the date range error
        date_errors = [e for e in errors if "date" in e.message.lower()]
        assert len(date_errors) > 0

    def test_profile_with_new_style_rules(self, tmp_path: Path) -> None:
        """Profile with spec_version 0.3 and explicit rule types loads correctly."""
        content = """
spec_version: "0.3"
name: test-profile
version: "1.0"
entities:
  Study:
    fields:
      - name: identifier
        type: string
        required: true
      - name: start_date
        type: date
      - name: end_date
        type: date
validation_rules:
  - name: study_dates
    type: date_range
    applies_to: [Study]
    start_field: start_date
    end_field: end_date
    message: "End date must be after start date"
"""
        # Create profile structure
        profile_dir = tmp_path / "test-profile" / "1.0"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.yaml").write_text(content)

        loader = SpecLoader(profile="test-profile")
        loader._user_specs_dir = tmp_path

        profile = loader.load_profile(version="1.0", profile="test-profile")
        assert profile.spec_version == "0.3"
        assert len(profile.validation_rules) == 1

        rule = profile.validation_rules[0]
        assert rule.type == "date_range"
        assert rule.start_field == "start_date"
        assert rule.end_field == "end_date"
        assert rule.message == "End date must be after start date"

    def test_mixed_old_new_rules_both_work(self, tmp_path: Path) -> None:
        """Profile with both old-style and new-style rules works."""
        content = """
spec_version: "0.3"
name: test-profile
version: "1.0"
entities:
  Study:
    fields:
      - name: identifier
        type: string
        required: true
      - name: start_date
        type: date
      - name: end_date
        type: date
      - name: email
        type: string
      - name: phone
        type: string
validation_rules:
  # New style with explicit type
  - name: study_dates
    type: date_range
    applies_to: [Study]
    start_field: start_date
    end_field: end_date
  # Old style without type (inferred)
  - name: contact_info
    applies_to: [Study]
    condition: "email OR phone"
"""
        profile_dir = tmp_path / "test-profile" / "1.0"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.yaml").write_text(content)

        loader = SpecLoader(profile="test-profile")
        loader._user_specs_dir = tmp_path

        profile = loader.load_profile(version="1.0", profile="test-profile")
        assert len(profile.validation_rules) == 2

        # First rule has explicit type
        assert profile.validation_rules[0].type == "date_range"

        # Second rule has no explicit type (inferred)
        assert profile.validation_rules[1].type is None
        assert profile.validation_rules[1].condition == "email OR phone"
