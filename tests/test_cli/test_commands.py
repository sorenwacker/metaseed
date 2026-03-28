"""Tests for CLI commands."""

from pathlib import Path

from typer.testing import CliRunner

from miappe_api.cli import app

runner = CliRunner()


class TestVersionCommand:
    """Tests for version command."""

    def test_version_shows_version(self) -> None:
        """Version command displays version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "miappe-api" in result.stdout
        assert "0.1.0" in result.stdout


class TestValidateCommand:
    """Tests for validate command."""

    def test_validate_valid_file(self, tmp_path: Path) -> None:
        """Validate valid YAML file."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test investigation
contacts:
  - name: Test Contact
studies:
  - unique_id: STU001
    title: Test Study
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["validate", str(file_path), "--entity", "investigation"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower() or "passed" in result.stdout.lower()

    def test_validate_missing_required_field(self, tmp_path: Path) -> None:
        """Validate file missing required field shows error."""
        content = """
unique_id: INV001
# missing title
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["validate", str(file_path), "--entity", "investigation"])
        assert "title" in result.stdout.lower()

    def test_validate_nonexistent_file(self) -> None:
        """Validate nonexistent file shows error."""
        result = runner.invoke(
            app, ["validate", "/nonexistent/file.yaml", "--entity", "investigation"]
        )
        assert result.exit_code != 0 or "error" in result.stdout.lower()


class TestTemplateCommand:
    """Tests for template command."""

    def test_template_to_stdout(self) -> None:
        """Generate template to stdout."""
        result = runner.invoke(app, ["template", "investigation"])
        assert result.exit_code == 0
        assert "unique_id" in result.stdout
        assert "title" in result.stdout

    def test_template_to_file(self, tmp_path: Path) -> None:
        """Generate template to file."""
        output_path = tmp_path / "template.yaml"
        result = runner.invoke(app, ["template", "investigation", "-o", str(output_path)])
        assert result.exit_code == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "unique_id" in content
        assert "title" in content

    def test_template_json_format(self, tmp_path: Path) -> None:
        """Generate template in JSON format."""
        output_path = tmp_path / "template.json"
        result = runner.invoke(
            app, ["template", "investigation", "-o", str(output_path), "--format", "json"]
        )
        assert result.exit_code == 0
        content = output_path.read_text()
        assert "{" in content  # JSON has braces


class TestConvertCommand:
    """Tests for convert command."""

    def test_convert_yaml_to_json(self, tmp_path: Path) -> None:
        """Convert YAML to JSON."""
        yaml_content = """
unique_id: INV001
title: Test Investigation
"""
        input_path = tmp_path / "input.yaml"
        input_path.write_text(yaml_content)
        output_path = tmp_path / "output.json"

        result = runner.invoke(
            app,
            ["convert", str(input_path), str(output_path), "--entity", "investigation"],
        )
        assert result.exit_code == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "{" in content
        assert "INV001" in content

    def test_convert_json_to_yaml(self, tmp_path: Path) -> None:
        """Convert JSON to YAML."""
        json_content = '{"unique_id": "INV001", "title": "Test Investigation"}'
        input_path = tmp_path / "input.json"
        input_path.write_text(json_content)
        output_path = tmp_path / "output.yaml"

        result = runner.invoke(
            app,
            ["convert", str(input_path), str(output_path), "--entity", "investigation"],
        )
        assert result.exit_code == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "{" not in content  # YAML shouldn't have braces


class TestEntitiesCommand:
    """Tests for entities command."""

    def test_list_entities(self) -> None:
        """List available entities."""
        result = runner.invoke(app, ["entities"])
        assert result.exit_code == 0
        assert "investigation" in result.stdout.lower()
        assert "study" in result.stdout.lower()
        assert "person" in result.stdout.lower()

    def test_list_entities_with_version(self) -> None:
        """List entities for specific version."""
        result = runner.invoke(app, ["entities", "--version", "1.1"])
        assert result.exit_code == 0
        assert "investigation" in result.stdout.lower()
