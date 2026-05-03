"""Tests for report generators."""

import pytest

from metaseed.specs.merge import (
    CSVReportGenerator,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    compare,
)


@pytest.fixture
def comparison():
    """Create a comparison result for testing."""
    return compare([("miappe", "1.1"), ("isa", "1.0")])


class TestMarkdownReportGenerator:
    """Tests for MarkdownReportGenerator."""

    def test_generate_returns_string(self, comparison) -> None:
        """Report generator returns a string."""
        report = MarkdownReportGenerator(comparison).generate()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_contains_header(self, comparison) -> None:
        """Report contains comparison header."""
        report = MarkdownReportGenerator(comparison).generate()
        assert "# Profile Comparison Report" in report

    def test_report_contains_profiles(self, comparison) -> None:
        """Report lists compared profiles."""
        report = MarkdownReportGenerator(comparison).generate()
        assert "miappe/1.1" in report
        assert "isa/1.0" in report

    def test_report_contains_statistics(self, comparison) -> None:
        """Report includes statistics section."""
        report = MarkdownReportGenerator(comparison).generate()
        assert "Summary Statistics" in report
        assert "Total entities" in report

    def test_report_contains_entity_table(self, comparison) -> None:
        """Report includes entity comparison table."""
        report = MarkdownReportGenerator(comparison).generate()
        assert "Entity Comparison" in report
        assert "| Entity |" in report


class TestCSVReportGenerator:
    """Tests for CSVReportGenerator."""

    def test_generate_returns_string(self, comparison) -> None:
        """Report generator returns a string."""
        report = CSVReportGenerator(comparison).generate()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_has_header_row(self, comparison) -> None:
        """CSV has header row."""
        report = CSVReportGenerator(comparison).generate()
        lines = report.strip().split("\n")
        assert len(lines) > 1
        assert "Entity" in lines[0]

    def test_report_is_valid_csv(self, comparison) -> None:
        """Report is valid CSV format."""
        import csv
        import io

        report = CSVReportGenerator(comparison).generate()
        reader = csv.reader(io.StringIO(report))
        rows = list(reader)
        assert len(rows) > 1
        # CSV should be parseable (multi-section CSV may have varying columns)
        # Just verify we have data rows
        non_empty_rows = [r for r in rows if any(cell.strip() for cell in r)]
        assert len(non_empty_rows) > 0


class TestHTMLReportGenerator:
    """Tests for HTMLReportGenerator."""

    def test_generate_returns_string(self, comparison) -> None:
        """Report generator returns a string."""
        report = HTMLReportGenerator(comparison).generate()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_is_valid_html(self, comparison) -> None:
        """Report contains HTML structure."""
        report = HTMLReportGenerator(comparison).generate()
        assert "<html" in report or "<!DOCTYPE" in report.upper()
        assert "</html>" in report

    def test_report_contains_title(self, comparison) -> None:
        """Report contains title."""
        report = HTMLReportGenerator(comparison).generate()
        assert "<title>" in report or "Profile Comparison" in report

    def test_report_contains_table(self, comparison) -> None:
        """Report contains comparison table."""
        report = HTMLReportGenerator(comparison).generate()
        assert "<table" in report
        assert "</table>" in report
