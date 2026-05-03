"""Tests that verify documented CLI behavior in docs/guides/spec-merge.md.

These tests validate that the CLI commands work as documented.
"""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from metaseed.cli import app

runner = CliRunner()


class TestDocumentedCompareCommand:
    """Tests for documented compare CLI behavior.

    Docs section: (implied from merge command documentation pattern)
    """

    def test_compare_two_profiles(self) -> None:
        """CLI accepts two profile/version arguments."""
        result = runner.invoke(app, ["compare", "miappe/1.1", "isa/1.0"])
        assert result.exit_code == 0

    def test_compare_output_to_file(self) -> None:
        """CLI supports -o flag for output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "diff.md"
            result = runner.invoke(
                app,
                ["compare", "miappe/1.1", "isa/1.0", "-o", str(output)],
            )
            assert result.exit_code == 0
            assert output.exists()

    def test_compare_markdown_format(self) -> None:
        """CLI supports -f markdown format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "diff.md"
            result = runner.invoke(
                app,
                ["compare", "miappe/1.1", "isa/1.0", "-o", str(output), "-f", "markdown"],
            )
            assert result.exit_code == 0

    def test_compare_csv_format(self) -> None:
        """CLI supports -f csv format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "diff.csv"
            result = runner.invoke(
                app,
                ["compare", "miappe/1.1", "isa/1.0", "-o", str(output), "-f", "csv"],
            )
            assert result.exit_code == 0

    def test_compare_html_format(self) -> None:
        """CLI supports -f html format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "diff.html"
            result = runner.invoke(
                app,
                ["compare", "miappe/1.1", "isa/1.0", "-o", str(output), "-f", "html"],
            )
            assert result.exit_code == 0


class TestDocumentedMergeCommand:
    """Tests for documented merge CLI behavior.

    Docs section: Profile Merging > CLI Usage
    """

    def test_basic_merge(self) -> None:
        """Documented: metaseed merge miappe/1.1 isa/1.0 -o combined.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "combined.yaml"
            result = runner.invoke(
                app,
                ["merge", "miappe/1.1", "isa/1.0", "-o", str(output)],
            )
            assert result.exit_code == 0
            assert output.exists()
            content = output.read_text()
            assert "version:" in content

    def test_merge_with_most_restrictive_strategy(self) -> None:
        """Documented: metaseed merge ... -s most_restrictive -o strict.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "strict.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-s",
                    "most_restrictive",
                    "-o",
                    str(output),
                ],
            )
            assert result.exit_code == 0
            assert "most_restrictive" in result.stdout

    def test_merge_with_custom_name_and_version(self) -> None:
        """Documented: metaseed merge ... -n miappe-extended -v 2.0 -o extended.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "extended.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-n",
                    "miappe-extended",
                    "-v",
                    "2.0",
                    "-o",
                    str(output),
                ],
            )
            assert result.exit_code == 0
            content = output.read_text()
            assert "miappe-extended" in content
            assert "version: '2.0'" in content

    def test_merge_with_prefer_strategy(self) -> None:
        """Documented: metaseed merge ... -s prefer_miappe/1.1 -o miappe-based.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "miappe-based.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-s",
                    "prefer_miappe/1.1",
                    "-o",
                    str(output),
                ],
            )
            assert result.exit_code == 0
            assert output.exists()

    def test_merge_first_wins_is_default(self) -> None:
        """Documented: default strategy is first_wins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "default.yaml"
            result = runner.invoke(
                app,
                ["merge", "miappe/1.1", "isa/1.0", "-o", str(output)],
            )
            assert result.exit_code == 0
            # Default should work without specifying strategy

    def test_merge_last_wins_strategy(self) -> None:
        """Strategy: last_wins - Use last profile's values for conflicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "last.yaml"
            result = runner.invoke(
                app,
                ["merge", "miappe/1.1", "isa/1.0", "-s", "last_wins", "-o", str(output)],
            )
            assert result.exit_code == 0
            assert "last_wins" in result.stdout

    def test_merge_least_restrictive_strategy(self) -> None:
        """Strategy: least_restrictive - required=False wins, looser constraints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "loose.yaml"
            result = runner.invoke(
                app,
                [
                    "merge",
                    "miappe/1.1",
                    "isa/1.0",
                    "-s",
                    "least_restrictive",
                    "-o",
                    str(output),
                ],
            )
            assert result.exit_code == 0
            assert "least_restrictive" in result.stdout
