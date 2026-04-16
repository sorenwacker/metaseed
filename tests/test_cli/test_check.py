"""Tests for the check CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from metaseed.cli import app

runner = CliRunner()


class TestCheckCommand:
    """Tests for check command."""

    def test_check_valid_file(self, tmp_path: Path) -> None:
        """Check valid file returns success."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - investigation_id: INV001
    name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path)])
        assert result.exit_code == 0
        assert "passed" in result.stdout.lower()

    def test_check_invalid_file(self, tmp_path: Path) -> None:
        """Check invalid file returns error."""
        content = """
unique_id: INV001
# missing title
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path)])
        assert result.exit_code == 1
        assert "title" in result.stdout.lower()

    def test_check_nonexistent_file(self) -> None:
        """Check nonexistent file returns input error."""
        result = runner.invoke(app, ["check", "/nonexistent/file.yaml"])
        assert result.exit_code == 2
        # Error message may be in stdout or stderr
        output = (result.stdout + (result.stderr or "")).lower()
        assert "not found" in output or "error" in output

    def test_check_directory(self, tmp_path: Path) -> None:
        """Check directory with valid files."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
"""
        (tmp_path / "investigation.yaml").write_text(content)

        result = runner.invoke(app, ["check", str(tmp_path)])
        assert result.exit_code == 0

    def test_check_empty_directory(self, tmp_path: Path) -> None:
        """Check empty directory shows warning but succeeds."""
        result = runner.invoke(app, ["check", str(tmp_path)])
        assert result.exit_code == 0  # Warnings don't cause failure
        assert "no yaml" in result.stdout.lower() or "warning" in result.stdout.lower()

    def test_check_with_profile(self, tmp_path: Path) -> None:
        """Check with explicit profile option."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(
            app, ["check", str(file_path), "--profile", "miappe", "--version", "1.1"]
        )
        assert result.exit_code == 0

    def test_check_invalid_profile(self, tmp_path: Path) -> None:
        """Check with invalid profile returns config error."""
        content = "unique_id: INV001"
        file_path = tmp_path / "test.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path), "--profile", "nonexistent_profile"])
        assert result.exit_code == 3
        # Error message may be in stdout or stderr
        output = (result.stdout + (result.stderr or "")).lower()
        assert "unknown profile" in output or "error" in output

    def test_check_verbose(self, tmp_path: Path) -> None:
        """Check with verbose option shows details."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path), "--verbose"])
        assert result.exit_code == 0
        # Verbose should show files checked and/or entity counts
        assert "files" in result.stdout.lower() or "investigation" in result.stdout.lower()

    def test_check_quiet_valid(self, tmp_path: Path) -> None:
        """Check with quiet option suppresses success output."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path), "--quiet"])
        assert result.exit_code == 0
        assert result.stdout.strip() == ""

    def test_check_quiet_invalid(self, tmp_path: Path) -> None:
        """Check with quiet option still shows errors."""
        content = """
unique_id: INV001
# missing title
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path), "--quiet"])
        assert result.exit_code == 1
        # Errors should still be shown even with quiet
        assert len(result.stdout.strip()) > 0

    def test_check_invalid_yaml(self, tmp_path: Path) -> None:
        """Check file with invalid YAML syntax."""
        content = """
unique_id: INV001
  bad_indent: invalid
"""
        file_path = tmp_path / "invalid.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path)])
        assert result.exit_code == 1


class TestProfilesCommand:
    """Tests for profiles command."""

    def test_profiles_list(self) -> None:
        """List profiles shows available profiles."""
        result = runner.invoke(app, ["profiles"])
        assert result.exit_code == 0
        assert "miappe" in result.stdout.lower()

    def test_profiles_verbose(self) -> None:
        """Profiles with verbose shows versions."""
        result = runner.invoke(app, ["profiles", "--verbose"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()

    def test_profiles_default_marker(self) -> None:
        """Profiles shows default marker."""
        result = runner.invoke(app, ["profiles"])
        assert result.exit_code == 0
        assert "default" in result.stdout.lower()


class TestExitCodes:
    """Tests for CLI exit codes."""

    def test_exit_code_success(self, tmp_path: Path) -> None:
        """Exit code 0 for success."""
        content = """
unique_id: INV001
title: Test Investigation
description: A test
contacts:
  - name: Test Person
studies:
  - unique_id: STU001
    investigation_id: INV001
    title: Test Study
"""
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path)])
        assert result.exit_code == 0

    def test_exit_code_validation_error(self, tmp_path: Path) -> None:
        """Exit code 1 for validation errors."""
        content = "unique_id: INV001"  # missing title
        file_path = tmp_path / "investigation.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path)])
        assert result.exit_code == 1

    def test_exit_code_input_error(self) -> None:
        """Exit code 2 for input errors (file not found)."""
        result = runner.invoke(app, ["check", "/nonexistent/path"])
        assert result.exit_code == 2

    def test_exit_code_config_error(self, tmp_path: Path) -> None:
        """Exit code 3 for config errors (unknown profile)."""
        content = "unique_id: INV001"
        file_path = tmp_path / "test.yaml"
        file_path.write_text(content)

        result = runner.invoke(app, ["check", str(file_path), "--profile", "nonexistent"])
        assert result.exit_code == 3
