"""Tests for the CLI module."""

import json

import yaml
from typer.testing import CliRunner

from metaseed.cli import app

runner = CliRunner()


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_shows_version(self):
        """Version command shows package version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "metaseed" in result.output


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_file_not_found(self, tmp_path):
        """Validate returns error for missing file."""
        result = runner.invoke(app, ["validate", str(tmp_path / "missing.yaml")])
        assert result.exit_code == 2  # EXIT_INPUT_ERROR
        output = result.output + (result.stderr or "")
        assert "File not found" in output or "not found" in output.lower()

    def test_validate_invalid_yaml(self, tmp_path):
        """Validate returns error for invalid YAML."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("invalid: yaml: content: ][", encoding="utf-8")

        result = runner.invoke(app, ["validate", str(bad_yaml)])
        assert result.exit_code == 2  # EXIT_INPUT_ERROR
        output = result.output + (result.stderr or "")
        assert "Invalid YAML" in output or "yaml" in output.lower()

    def test_validate_empty_yaml(self, tmp_path):
        """Validate handles empty YAML file."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("", encoding="utf-8")

        result = runner.invoke(app, ["validate", str(empty_yaml)])
        # Empty file should have validation errors (missing required fields)
        assert result.exit_code == 1

    def test_validate_valid_investigation(self, tmp_path):
        """Validate passes for valid investigation."""
        valid_yaml = tmp_path / "investigation.yaml"
        data = {
            "unique_id": "INV-001",
            "title": "Test Investigation",
            "studies": [
                {"unique_id": "STU-001", "title": "Study 1", "investigation_id": "INV-001"}
            ],
            "contacts": [{"name": "John Doe", "investigation_id": "INV-001"}],
        }
        valid_yaml.write_text(yaml.dump(data), encoding="utf-8")

        result = runner.invoke(app, ["validate", str(valid_yaml), "-e", "investigation"])
        assert result.exit_code == 0
        assert "Validation passed" in result.output

    def test_validate_with_errors(self, tmp_path):
        """Validate shows errors for invalid data."""
        invalid_yaml = tmp_path / "invalid.yaml"
        data = {"description": "Missing required fields"}
        invalid_yaml.write_text(yaml.dump(data), encoding="utf-8")

        result = runner.invoke(app, ["validate", str(invalid_yaml), "-e", "investigation"])
        assert result.exit_code == 1
        assert "Validation failed" in result.output

    def test_validate_with_version_option(self, tmp_path):
        """Validate accepts version option."""
        valid_yaml = tmp_path / "investigation.yaml"
        data = {
            "unique_id": "INV-001",
            "title": "Test Investigation",
            "studies": [
                {"unique_id": "STU-001", "title": "Study 1", "investigation_id": "INV-001"}
            ],
            "contacts": [{"name": "John Doe", "investigation_id": "INV-001"}],
        }
        valid_yaml.write_text(yaml.dump(data), encoding="utf-8")

        result = runner.invoke(
            app, ["validate", str(valid_yaml), "-e", "investigation", "-v", "1.1"]
        )
        assert result.exit_code == 0


class TestTemplateCommand:
    """Tests for the template command."""

    def test_template_outputs_yaml(self):
        """Template outputs YAML to stdout."""
        result = runner.invoke(app, ["template", "investigation"])
        assert result.exit_code == 0
        # Should contain required field placeholders
        assert "unique_id" in result.output or "title" in result.output

    def test_template_outputs_json(self):
        """Template outputs JSON format."""
        result = runner.invoke(app, ["template", "investigation", "-f", "json"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_template_writes_to_file(self, tmp_path):
        """Template writes to output file."""
        output_file = tmp_path / "template.yaml"
        result = runner.invoke(app, ["template", "investigation", "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        assert "Template written to" in result.output

    def test_template_creates_parent_directories(self, tmp_path):
        """Template creates parent directories for output."""
        output_file = tmp_path / "nested" / "dir" / "template.yaml"
        result = runner.invoke(app, ["template", "investigation", "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_template_unknown_entity(self):
        """Template returns error for unknown entity."""
        result = runner.invoke(app, ["template", "unknown_entity"])
        assert result.exit_code == 3  # EXIT_CONFIG_ERROR
        output = result.output + (result.stderr or "")
        assert "Error" in output or "error" in output.lower()

    def test_template_with_version_option(self):
        """Template accepts version option."""
        result = runner.invoke(app, ["template", "investigation", "-v", "1.1"])
        assert result.exit_code == 0


class TestConvertCommand:
    """Tests for the convert command."""

    def test_convert_yaml_to_json(self, tmp_path):
        """Convert YAML to JSON."""
        input_file = tmp_path / "input.yaml"
        output_file = tmp_path / "output.json"

        data = {"unique_id": "INV-001", "title": "Test Investigation"}
        input_file.write_text(yaml.dump(data), encoding="utf-8")

        result = runner.invoke(
            app, ["convert", str(input_file), str(output_file), "-e", "investigation"]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        assert "Converted" in result.output

        # Verify JSON content
        output_data = json.loads(output_file.read_text())
        assert output_data["unique_id"] == "INV-001"

    def test_convert_json_to_yaml(self, tmp_path):
        """Convert JSON to YAML."""
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.yaml"

        data = {"unique_id": "INV-001", "title": "Test Investigation"}
        input_file.write_text(json.dumps(data), encoding="utf-8")

        result = runner.invoke(
            app, ["convert", str(input_file), str(output_file), "-e", "investigation"]
        )
        assert result.exit_code == 0
        assert output_file.exists()

        # Verify YAML content
        output_data = yaml.safe_load(output_file.read_text())
        assert output_data["unique_id"] == "INV-001"

    def test_convert_file_not_found(self, tmp_path):
        """Convert returns error for missing input file."""
        result = runner.invoke(
            app, ["convert", str(tmp_path / "missing.yaml"), str(tmp_path / "output.json")]
        )
        assert result.exit_code == 2  # EXIT_INPUT_ERROR
        output = result.output + (result.stderr or "")
        assert "File not found" in output or "not found" in output.lower()

    def test_convert_unknown_input_format(self, tmp_path):
        """Convert returns error for unknown input format."""
        input_file = tmp_path / "input.txt"
        input_file.write_text("data", encoding="utf-8")

        result = runner.invoke(app, ["convert", str(input_file), str(tmp_path / "output.json")])
        assert result.exit_code == 1
        assert "Unknown input format" in result.output

    def test_convert_unknown_output_format(self, tmp_path):
        """Convert returns error for unknown output format."""
        input_file = tmp_path / "input.yaml"
        input_file.write_text(
            yaml.dump({"unique_id": "INV-001", "title": "Test"}), encoding="utf-8"
        )

        result = runner.invoke(app, ["convert", str(input_file), str(tmp_path / "output.txt")])
        assert result.exit_code == 1
        assert "Unknown output format" in result.output

    def test_convert_unknown_entity(self, tmp_path):
        """Convert returns error for unknown entity type."""
        input_file = tmp_path / "input.yaml"
        input_file.write_text(yaml.dump({"unique_id": "TEST-001"}), encoding="utf-8")

        result = runner.invoke(
            app, ["convert", str(input_file), str(tmp_path / "output.json"), "-e", "unknown"]
        )
        assert result.exit_code == 3  # EXIT_CONFIG_ERROR
        output = result.output + (result.stderr or "")
        assert "Error" in output or "error" in output.lower()

    def test_convert_invalid_data(self, tmp_path):
        """Convert returns error for invalid data."""
        input_file = tmp_path / "input.yaml"
        input_file.write_text("invalid: yaml: ][", encoding="utf-8")

        result = runner.invoke(
            app, ["convert", str(input_file), str(tmp_path / "output.json"), "-e", "investigation"]
        )
        assert result.exit_code == 2  # EXIT_INPUT_ERROR


class TestEntitiesCommand:
    """Tests for the entities command."""

    def test_entities_lists_entities(self):
        """Entities command lists available entities."""
        result = runner.invoke(app, ["entities"])
        assert result.exit_code == 0
        assert "Available entities" in result.output
        assert "investigation" in result.output.lower()

    def test_entities_with_version_option(self):
        """Entities accepts version option."""
        result = runner.invoke(app, ["entities", "-v", "1.1"])
        assert result.exit_code == 0
        assert "miappe v1.1" in result.output.lower()

    def test_entities_invalid_version(self):
        """Entities returns error for invalid version."""
        result = runner.invoke(app, ["entities", "-v", "99.99"])
        assert result.exit_code == 3  # EXIT_CONFIG_ERROR
        output = result.output + (result.stderr or "")
        assert "Error" in output or "error" in output.lower()


class TestImportCommand:
    """Tests for the import command."""

    def test_import_isa_json(self, tmp_path):
        """Import ISA-JSON file."""
        isa_json = tmp_path / "investigation.json"
        data = {
            "identifier": "INV-001",
            "title": "Test Investigation",
            "studies": [],
        }
        isa_json.write_text(json.dumps(data), encoding="utf-8")

        result = runner.invoke(app, ["import", str(isa_json)])
        assert result.exit_code == 0
        assert "Imported ISA-JSON" in result.output

    def test_import_isa_json_with_output(self, tmp_path):
        """Import ISA-JSON with output directory."""
        isa_json = tmp_path / "investigation.json"
        output_dir = tmp_path / "output"
        data = {
            "identifier": "INV-001",
            "title": "Test Investigation",
            "studies": [{"identifier": "STU-001", "title": "Study 1"}],
        }
        isa_json.write_text(json.dumps(data), encoding="utf-8")

        result = runner.invoke(app, ["import", str(isa_json), "-o", str(output_dir)])
        assert result.exit_code == 0
        assert output_dir.exists()
        assert (output_dir / "investigation.yaml").exists()

    def test_import_isa_json_output_json_format(self, tmp_path):
        """Import ISA-JSON with JSON output format."""
        isa_json = tmp_path / "investigation.json"
        output_dir = tmp_path / "output"
        data = {
            "identifier": "INV-001",
            "title": "Test Investigation",
            "studies": [],
        }
        isa_json.write_text(json.dumps(data), encoding="utf-8")

        result = runner.invoke(app, ["import", str(isa_json), "-o", str(output_dir), "-f", "json"])
        assert result.exit_code == 0
        assert (output_dir / "investigation.json").exists()

    def test_import_invalid_path(self, tmp_path):
        """Import returns error for invalid path."""
        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("not json", encoding="utf-8")

        result = runner.invoke(app, ["import", str(invalid_file)])
        assert result.exit_code == 1
        assert "Error" in result.output or "must be" in result.output.lower()

    def test_import_isa_tab_directory(self, tmp_path):
        """Import ISA-Tab directory invokes the import path."""
        # Create minimal ISA-Tab structure
        isa_dir = tmp_path / "isa_tab"
        isa_dir.mkdir()
        # Empty investigation file to trigger ISA-Tab import path
        (isa_dir / "i_investigation.txt").write_text("", encoding="utf-8")

        result = runner.invoke(app, ["import", str(isa_dir)])
        # Should either succeed or show import error (tests that path is executed)
        assert result.exit_code in (0, 1)
        assert "Imported ISA-Tab" in result.output or "Error" in result.output

    def test_import_invalid_json(self, tmp_path):
        """Import returns error for invalid JSON."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json}", encoding="utf-8")

        result = runner.invoke(app, ["import", str(bad_json)])
        assert result.exit_code == 1


class TestNoArgsHelp:
    """Tests for no-args-is-help behavior."""

    def test_no_args_shows_help(self):
        """Running without arguments shows help."""
        result = runner.invoke(app, [])
        # Exit code 2 is standard for "missing arguments/help shown"
        assert result.exit_code in (0, 2)
        assert "Usage" in result.output or "metaseed" in result.output


class TestHelpOptions:
    """Tests for help options on commands."""

    def test_validate_help(self):
        """Validate --help shows usage."""
        result = runner.invoke(app, ["validate", "--help"])
        assert result.exit_code == 0
        assert "Validate" in result.output

    def test_template_help(self):
        """Template --help shows usage."""
        result = runner.invoke(app, ["template", "--help"])
        assert result.exit_code == 0
        assert "template" in result.output.lower()

    def test_convert_help(self):
        """Convert --help shows usage."""
        result = runner.invoke(app, ["convert", "--help"])
        assert result.exit_code == 0
        assert "Convert" in result.output

    def test_entities_help(self):
        """Entities --help shows usage."""
        result = runner.invoke(app, ["entities", "--help"])
        assert result.exit_code == 0
        assert "entities" in result.output.lower()

    def test_import_help(self):
        """Import --help shows usage."""
        result = runner.invoke(app, ["import", "--help"])
        assert result.exit_code == 0
        assert "Import" in result.output

    def test_compare_help(self):
        """Compare --help shows usage."""
        result = runner.invoke(app, ["compare", "--help"])
        assert result.exit_code == 0
        assert "Compare" in result.output

    def test_merge_help(self):
        """Merge --help shows usage."""
        result = runner.invoke(app, ["merge", "--help"])
        assert result.exit_code == 0
        assert "Merge" in result.output


class TestCompareCommand:
    """Tests for the compare command."""

    def test_compare_two_profiles(self):
        """Compare two profiles outputs markdown."""
        result = runner.invoke(app, ["compare", "miappe/1.1", "isa/1.0"])
        assert result.exit_code == 0
        assert "Profile Comparison Report" in result.output
        assert "miappe/1.1" in result.output
        assert "isa/1.0" in result.output

    def test_compare_requires_two_profiles(self):
        """Compare requires at least two profiles."""
        result = runner.invoke(app, ["compare", "miappe/1.1"])
        assert result.exit_code != 0

    def test_compare_invalid_profile_format(self):
        """Compare rejects invalid profile format."""
        result = runner.invoke(app, ["compare", "invalid", "miappe/1.1"])
        assert result.exit_code != 0

    def test_compare_unknown_profile(self):
        """Compare rejects unknown profiles."""
        result = runner.invoke(app, ["compare", "unknown/1.0", "miappe/1.1"])
        assert result.exit_code != 0

    def test_compare_output_to_file(self, tmp_path):
        """Compare writes to output file."""
        output_file = tmp_path / "comparison.md"
        result = runner.invoke(app, ["compare", "miappe/1.1", "isa/1.0", "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "Profile Comparison Report" in content

    def test_compare_csv_format(self, tmp_path):
        """Compare outputs CSV format."""
        output_file = tmp_path / "comparison.csv"
        result = runner.invoke(
            app, ["compare", "miappe/1.1", "isa/1.0", "-f", "csv", "-o", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "," in content  # CSV has commas

    def test_compare_html_format(self, tmp_path):
        """Compare outputs HTML format."""
        output_file = tmp_path / "comparison.html"
        result = runner.invoke(
            app, ["compare", "miappe/1.1", "isa/1.0", "-f", "html", "-o", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "<html" in content or "<table" in content

    def test_compare_multiple_profiles(self):
        """Compare supports more than two profiles."""
        result = runner.invoke(app, ["compare", "miappe/1.1", "isa/1.0", "jerm/1.0"])
        assert result.exit_code == 0
        assert "Profile Comparison Report" in result.output


class TestMergeCommand:
    """Tests for the merge command."""

    def test_merge_two_profiles(self, tmp_path):
        """Merge two profiles creates YAML output."""
        output_file = tmp_path / "merged.yaml"
        result = runner.invoke(app, ["merge", "miappe/1.1", "isa/1.0", "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        assert "Merged profile written to" in result.output

        # Verify it's valid YAML with expected structure
        import yaml

        content = yaml.safe_load(output_file.read_text())
        assert "entities" in content
        assert "version" in content

    def test_merge_requires_two_profiles(self):
        """Merge requires at least two profiles."""
        result = runner.invoke(app, ["merge", "miappe/1.1"])
        assert result.exit_code != 0

    def test_merge_with_strategy(self, tmp_path):
        """Merge accepts strategy option."""
        output_file = tmp_path / "merged.yaml"
        result = runner.invoke(
            app,
            [
                "merge",
                "miappe/1.1",
                "isa/1.0",
                "-s",
                "most_restrictive",
                "-o",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert "most_restrictive" in result.output

    def test_merge_with_custom_name(self, tmp_path):
        """Merge accepts custom name option."""
        output_file = tmp_path / "merged.yaml"
        result = runner.invoke(
            app,
            ["merge", "miappe/1.1", "isa/1.0", "-n", "my-custom-profile", "-o", str(output_file)],
        )
        assert result.exit_code == 0

        import yaml

        content = yaml.safe_load(output_file.read_text())
        assert content["name"] == "my-custom-profile"

    def test_merge_with_custom_version(self, tmp_path):
        """Merge accepts custom version option."""
        output_file = tmp_path / "merged.yaml"
        result = runner.invoke(
            app,
            ["merge", "miappe/1.1", "isa/1.0", "-v", "2.5", "-o", str(output_file)],
        )
        assert result.exit_code == 0

        import yaml

        content = yaml.safe_load(output_file.read_text())
        assert content["version"] == "2.5"

    def test_merge_invalid_strategy(self, tmp_path):
        """Merge rejects invalid strategy."""
        output_file = tmp_path / "merged.yaml"
        result = runner.invoke(
            app,
            ["merge", "miappe/1.1", "isa/1.0", "-s", "invalid_strategy", "-o", str(output_file)],
        )
        assert result.exit_code != 0

    def test_merge_prefer_strategy(self, tmp_path):
        """Merge supports prefer_<profile> strategy."""
        output_file = tmp_path / "merged.yaml"
        result = runner.invoke(
            app,
            [
                "merge",
                "miappe/1.1",
                "isa/1.0",
                "-s",
                "prefer_miappe/1.1",
                "-o",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
