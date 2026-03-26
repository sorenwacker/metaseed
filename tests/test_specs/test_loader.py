"""Tests for spec loader."""

from pathlib import Path

import pytest

from miappe_api.specs.loader import SpecLoader, SpecLoadError
from miappe_api.specs.schema import EntitySpec, FieldType


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

    def test_load_fields_parsed_correctly(self, loader: SpecLoader, valid_spec_yaml: Path) -> None:
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
        assert "parse" in str(exc_info.value).lower() or "yaml" in str(exc_info.value).lower()

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
