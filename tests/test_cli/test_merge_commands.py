"""Tests for compare and merge CLI commands."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from metaseed.cli import app

runner = CliRunner()


class TestCompareCommand:
    """Tests for the compare CLI command."""

    def test_compare_requires_two_profiles(self) -> None:
        """Compare requires at least 2 profiles."""
        result = runner.invoke(app, ["compare", "miappe/1.1"])
        assert result.exit_code != 0

    def test_compare_two_profiles(self) -> None:
        """Compare two profiles successfully."""
        result = runner.invoke(app, ["compare", "miappe/1.1", "isa/1.0"])
        assert result.exit_code == 0
        assert "Profile Comparison Report" in result.stdout

    def test_compare_outputs_statistics(self) -> None:
        """Compare output includes statistics."""
        result = runner.invoke(app, ["compare", "miappe/1.1", "isa/1.0"])
        assert result.exit_code == 0
        assert "Total entities" in result.stdout

    def test_compare_three_profiles(self) -> None:
        """Compare three profiles successfully."""
        result = runner.invoke(app, ["compare", "miappe/1.1", "miappe/1.2", "isa/1.0"])
        assert result.exit_code == 0

    def test_compare_output_to_file(self) -> None:
        """Compare can write to output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "diff.md"
            result = runner.invoke(
                app,
                ["compare", "miappe/1.1", "isa/1.0", "-o", str(output_path)],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text()
            assert "Profile Comparison Report" in content

    def test_compare_csv_format(self) -> None:
        """Compare can output CSV format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "diff.csv"
            result = runner.invoke(
                app,
                [
                    "compare",
                    "miappe/1.1",
                    "isa/1.0",
                    "-o",
                    str(output_path),
                    "-f",
                    "csv",
                ],
            )
            assert result.exit_code == 0
            assert output_path.exists()


class TestMergeCommand:
    """Tests for the merge CLI command."""

    def test_merge_requires_two_profiles(self) -> None:
        """Merge requires at least 2 profiles."""
        result = runner.invoke(app, ["merge", "miappe/1.1"])
        assert result.exit_code != 0

    def test_merge_two_profiles(self) -> None:
        """Merge two profiles successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "merged.yaml"
            result = runner.invoke(
                app,
                ["merge", "miappe/1.1", "isa/1.0", "-o", str(output_path)],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text()
            assert "version:" in content
            assert "entities:" in content

    def test_merge_with_strategy(self) -> None:
        """Merge with specific strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "merged.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-s",
                    "most_restrictive",
                    "-o",
                    str(output_path),
                ],
            )
            assert result.exit_code == 0
            assert "most_restrictive" in result.stdout

    def test_merge_with_custom_name(self) -> None:
        """Merge with custom profile name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "merged.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-n",
                    "my-custom-profile",
                    "-o",
                    str(output_path),
                ],
            )
            assert result.exit_code == 0
            content = output_path.read_text()
            assert "my-custom-profile" in content

    def test_merge_with_custom_version(self) -> None:
        """Merge with custom version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "merged.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-v",
                    "2.5",
                    "-o",
                    str(output_path),
                ],
            )
            assert result.exit_code == 0
            content = output_path.read_text()
            assert "version: '2.5'" in content

    def test_merge_reports_entity_count(self) -> None:
        """Merge output reports entity count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "merged.yaml"
            result = runner.invoke(
                app,
                ["merge", "miappe/1.1", "isa/1.0", "-o", str(output_path)],
            )
            assert result.exit_code == 0
            assert "Entities:" in result.stdout
