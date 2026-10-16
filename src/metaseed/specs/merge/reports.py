"""Report generators for profile comparisons.

This module provides generators for CSV, HTML, and Markdown reports
of profile comparison results.
"""

import csv
import io
from abc import ABC, abstractmethod
from typing import Any, Self

from metaseed.specs.schema import ValidationRuleSpec

from .models import ComparisonResult, DiffType


class ReportGenerator(ABC):
    """Base class for report generators."""

    def __init__(self: Self, comparison: ComparisonResult) -> None:
        """Initialize with comparison result.

        Args:
            comparison: ComparisonResult to report on.
        """
        self.comparison = comparison

    @abstractmethod
    def generate(self: Self) -> str:
        """Generate the report.

        Returns:
            Report content as string.
        """

    def _rule_rows(self: Self) -> list[tuple[str, list[str | None]]]:
        """Each differing rule with every profile's version, ``None`` if absent.

        Returns:
            ``(rule name, versions)``, versions ordered as the compared profiles.
        """
        return [
            (
                name,
                [
                    _rule_summary(by_profile.get(pid))
                    for pid in self.comparison.profiles
                ],
            )
            for name, by_profile in self.comparison.validation_rule_diffs.items()
        ]


def _rule_summary(rule: ValidationRuleSpec | None) -> str | None:
    """A rule's type and the parameters it sets, as ``key=value; ...``."""
    if rule is None:
        return None
    parts = []
    for key, value in rule.model_dump(exclude_none=True).items():
        if key == "name" or value in ("", []):
            continue
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        parts.append(f"{key}={shown}")
    return "; ".join(parts)


class CSVReportGenerator(ReportGenerator):
    """Generates CSV reports for profile comparisons."""

    def generate(self: Self) -> str:
        """Generate CSV report with entity and field comparison tables.

        Returns:
            CSV content as string.
        """
        output = io.StringIO()

        # Entity summary
        output.write("# Entity Comparison\n")
        self._write_entity_table(output)
        output.write("\n")

        # Field details
        output.write("# Field Comparison\n")
        self._write_field_table(output)

        rows = self._rule_rows()
        if rows:
            output.write("\n# Validation Rule Comparison\n")
            writer = csv.writer(output)
            writer.writerow(["Rule", *self.comparison.profiles])
            for name, versions in rows:
                writer.writerow([name, *(v or "" for v in versions)])

        return output.getvalue()

    def _write_entity_table(self: Self, output: io.StringIO) -> None:
        """Write entity comparison table.

        Args:
            output: StringIO to write to.
        """
        writer = csv.writer(output)

        # Header
        header = ["Entity", "Status"]
        header.extend(self.comparison.profiles)
        header.extend(["Fields", "Conflicts"])
        writer.writerow(header)

        # Data rows
        for ed in self.comparison.entity_diffs:
            row: list[Any] = [ed.entity_name, ed.diff_type.value]
            for profile_id in self.comparison.profiles:
                row.append("Y" if ed.profiles.get(profile_id, False) else "N")
            row.append(len(ed.field_diffs))
            row.append(len(ed.conflicting_fields))
            writer.writerow(row)

    def _write_field_table(self: Self, output: io.StringIO) -> None:
        """Write field comparison table.

        Args:
            output: StringIO to write to.
        """
        writer = csv.writer(output)

        # Header
        header = ["Entity", "Field", "Status", "Changed Attributes"]
        header.extend([f"{p} Type" for p in self.comparison.profiles])
        header.extend([f"{p} Required" for p in self.comparison.profiles])
        writer.writerow(header)

        # Data rows
        for ed in self.comparison.entity_diffs:
            for fd in ed.field_diffs:
                row = [
                    ed.entity_name,
                    fd.field_name,
                    fd.diff_type.value,
                    ", ".join(fd.attributes_changed),
                ]

                for profile_id in self.comparison.profiles:
                    spec = fd.profiles.get(profile_id)
                    row.append(spec.type.value if spec else "")

                for profile_id in self.comparison.profiles:
                    spec = fd.profiles.get(profile_id)
                    row.append(str(spec.required) if spec else "")

                writer.writerow(row)


class MarkdownReportGenerator(ReportGenerator):
    """Generates Markdown reports for profile comparisons."""

    def generate(self: Self) -> str:
        """Generate Markdown report.

        Returns:
            Markdown content as string.
        """
        lines: list[str] = []

        # Header
        lines.append("# Profile Comparison Report")
        lines.append("")
        lines.append(f"**Profiles compared:** {', '.join(self.comparison.profiles)}")
        lines.append("")

        # Statistics
        lines.append("## Summary Statistics")
        lines.append("")
        self._add_statistics_table(lines)
        lines.append("")

        # Entity comparison
        lines.append("## Entity Comparison")
        lines.append("")
        self._add_entity_table(lines)
        lines.append("")

        # Conflicts
        if self.comparison.conflicting_fields:
            lines.append("## Conflicts")
            lines.append("")
            self._add_conflicts_section(lines)
            lines.append("")

        # Every other changed field; conflicts have their own section above.
        lines.append("## Changed Fields")
        lines.append("")
        self._add_changed_fields_section(lines)

        rows = self._rule_rows()
        if rows:
            lines.append("")
            lines.append("## Validation Rule Differences")
            lines.append("")
            header = ["Rule", *self.comparison.profiles]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            for name, versions in rows:
                cells = [name, *(v if v is not None else "-" for v in versions)]
                lines.append(
                    "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"
                )

        return "\n".join(lines)

    def _add_statistics_table(self: Self, lines: list[str]) -> None:
        """Add statistics table to lines.

        Args:
            lines: List of lines to append to.
        """
        stats = self.comparison.statistics
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Total entities | {stats.total_entities} |")
        lines.append(f"| Common entities | {stats.common_entities} |")
        lines.append(f"| Unique entities | {stats.unique_entities} |")
        lines.append(f"| Modified entities | {stats.modified_entities} |")
        lines.append(f"| Total fields | {stats.total_fields} |")
        lines.append(f"| Common fields | {stats.common_fields} |")
        lines.append(f"| Modified fields | {stats.modified_fields} |")
        lines.append(f"| Conflicting fields | {stats.conflicting_fields} |")

    def _add_entity_table(self: Self, lines: list[str]) -> None:
        """Add entity comparison table to lines.

        Args:
            lines: List of lines to append to.
        """
        # Header
        header = ["Entity", "Status"]
        header.extend(self.comparison.profiles)
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # Rows
        for ed in sorted(self.comparison.entity_diffs, key=lambda x: x.entity_name):
            row = [ed.entity_name, self._status_icon(ed.diff_type)]
            for profile_id in self.comparison.profiles:
                present = ed.profiles.get(profile_id, False)
                row.append("Y" if present else "-")
            lines.append("| " + " | ".join(row) + " |")

    def _add_conflicts_section(self: Self, lines: list[str]) -> None:
        """Add conflicts section to lines.

        Args:
            lines: List of lines to append to.
        """
        for ed in self.comparison.entity_diffs:
            if not ed.conflicting_fields:
                continue

            lines.append(f"### {ed.entity_name}")
            lines.append("")

            for fd in ed.conflicting_fields:
                lines.append(f"**{fd.field_name}**")
                lines.append("")
                lines.append(
                    f"- Changed attributes: {', '.join(fd.attributes_changed)}"
                )

                for attr in fd.attributes_changed:
                    if attr in fd.values:
                        values = fd.values[attr]
                        lines.append(f"- {attr}:")
                        for profile_id, value in values.items():
                            lines.append(f"  - {profile_id}: `{value}`")

                lines.append("")

    def _add_changed_fields_section(self: Self, lines: list[str]) -> None:
        """Add the added, removed and modified fields to lines.

        Args:
            lines: List of lines to append to.
        """
        for ed in self.comparison.entity_diffs:
            modified = [
                fd
                for fd in ed.field_diffs
                if fd.diff_type in (DiffType.MODIFIED, DiffType.ADDED, DiffType.REMOVED)
            ]
            if not modified:
                continue

            lines.append(f"### {ed.entity_name}")
            lines.append("")

            # Header
            header = ["Field", "Status", "Changed"]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")

            for fd in modified:
                row = [
                    fd.field_name,
                    self._status_icon(fd.diff_type),
                    ", ".join(fd.attributes_changed) or "-",
                ]
                lines.append("| " + " | ".join(row) + " |")

            lines.append("")

    def _status_icon(self: Self, diff_type: DiffType) -> str:
        """Get status icon for diff type.

        Args:
            diff_type: Type of difference.

        Returns:
            Status indicator string.
        """
        icons = {
            DiffType.UNCHANGED: "=",
            DiffType.ADDED: "+",
            DiffType.REMOVED: "-",
            DiffType.MODIFIED: "~",
            DiffType.CONFLICT: "!",
        }
        return icons.get(diff_type, "?")


def _safe(value: object) -> str:
    """Profile text as page text, never as markup.

    Every value here comes from profile YAML, and profiles are not all
    first-party — a user directory or a hub-authored profile can carry
    `<script>`. The report is served as `text/html`, so an unescaped value
    would run in the reader's browser.
    """
    from html import escape

    return escape(str(value), quote=True)


class HTMLReportGenerator(ReportGenerator):
    """Generates styled HTML reports for profile comparisons."""

    def generate(self: Self) -> str:
        """Generate HTML report.

        Returns:
            HTML content as string.
        """
        lines: list[str] = []

        lines.append("<!DOCTYPE html>")
        lines.append("<html>")
        lines.append("<head>")
        lines.append("<meta charset='utf-8'>")
        lines.append("<title>Profile Comparison Report</title>")
        lines.append(self._get_styles())
        lines.append("</head>")
        lines.append("<body>")

        # Header
        lines.append("<h1>Profile Comparison Report</h1>")
        lines.append(
            f"<p>Profiles compared: <strong>{_safe(', '.join(self.comparison.profiles))}</strong></p>"
        )

        # Statistics
        lines.append("<h2>Summary Statistics</h2>")
        self._add_html_statistics(lines)

        # Entity table
        lines.append("<h2>Entity Comparison</h2>")
        self._add_html_entity_table(lines)

        # Conflicts
        if self.comparison.conflicting_fields:
            lines.append("<h2>Conflicts</h2>")
            self._add_html_conflicts(lines)

        # Field details
        lines.append("<h2>Field Details</h2>")
        self._add_html_field_details(lines)

        rows = self._rule_rows()
        if rows:
            lines.append("<h2>Validation Rule Differences</h2>")
            lines.append("<table>")
            lines.append(
                "<tr><th>Rule</th>"
                + "".join(f"<th>{_safe(p)}</th>" for p in self.comparison.profiles)
                + "</tr>"
            )
            for name, versions in rows:
                lines.append(
                    f"<tr><td>{_safe(name)}</td>"
                    + "".join(f"<td>{_safe(v or '-')}</td>" for v in versions)
                    + "</tr>"
                )
            lines.append("</table>")

        lines.append("</body>")
        lines.append("</html>")

        return "\n".join(lines)

    def _get_styles(self: Self) -> str:
        """Get CSS styles for the report.

        Returns:
            Style tag with CSS.
        """
        return """
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
        background: #f5f5f5;
    }
    h1, h2, h3 { color: #333; }
    table {
        border-collapse: collapse;
        width: 100%;
        background: white;
        margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    th, td {
        border: 1px solid #ddd;
        padding: 8px 12px;
        text-align: left;
    }
    th { background: #f0f0f0; font-weight: 600; }
    tr:nth-child(even) { background: #fafafa; }
    .unchanged { background: #e0e0e0; }
    .added { background: #c8e6c9; }
    .removed { background: #ffcdd2; }
    .modified { background: #fff3e0; }
    .conflict { background: #ffebee; border: 2px solid #d32f2f; }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
    }
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }
    .stat-card {
        background: white;
        padding: 16px;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .stat-value { font-size: 24px; font-weight: bold; color: #1976d2; }
    .stat-label { color: #666; font-size: 14px; }
</style>
"""

    def _add_html_statistics(self: Self, lines: list[str]) -> None:
        """Add HTML statistics section.

        Args:
            lines: List of lines to append to.
        """
        stats = self.comparison.statistics
        lines.append("<div class='stats-grid'>")

        stats_data = [
            ("Total Entities", stats.total_entities),
            ("Common Entities", stats.common_entities),
            ("Modified Entities", stats.modified_entities),
            ("Total Fields", stats.total_fields),
            ("Common Fields", stats.common_fields),
            ("Conflicting Fields", stats.conflicting_fields),
        ]

        for label, value in stats_data:
            lines.append(f"""
            <div class='stat-card'>
                <div class='stat-value'>{value}</div>
                <div class='stat-label'>{label}</div>
            </div>
            """)

        lines.append("</div>")

    def _add_html_entity_table(self: Self, lines: list[str]) -> None:
        """Add HTML entity table.

        Args:
            lines: List of lines to append to.
        """
        lines.append("<table>")
        lines.append("<tr>")
        lines.append("<th>Entity</th>")
        lines.append("<th>Status</th>")
        for profile_id in self.comparison.profiles:
            lines.append(f"<th>{_safe(profile_id)}</th>")
        lines.append("<th>Fields</th>")
        lines.append("<th>Conflicts</th>")
        lines.append("</tr>")

        for ed in sorted(self.comparison.entity_diffs, key=lambda x: x.entity_name):
            css_class = ed.diff_type.value
            lines.append(f"<tr class='{css_class}'>")
            lines.append(f"<td>{_safe(ed.entity_name)}</td>")
            lines.append(
                f"<td><span class='badge {css_class}'>{ed.diff_type.value}</span></td>"
            )

            for profile_id in self.comparison.profiles:
                present = ed.profiles.get(profile_id, False)
                lines.append(f"<td>{'Y' if present else '-'}</td>")

            lines.append(f"<td>{len(ed.field_diffs)}</td>")
            lines.append(f"<td>{len(ed.conflicting_fields)}</td>")
            lines.append("</tr>")

        lines.append("</table>")

    def _add_html_conflicts(self: Self, lines: list[str]) -> None:
        """Add HTML conflicts section.

        Args:
            lines: List of lines to append to.
        """
        for ed in self.comparison.entity_diffs:
            if not ed.conflicting_fields:
                continue

            lines.append(f"<h3>{_safe(ed.entity_name)}</h3>")

            for fd in ed.conflicting_fields:
                lines.append(
                    "<div class='conflict' style='padding: 12px; margin-bottom: 12px;'>"
                )
                lines.append(f"<strong>{_safe(fd.field_name)}</strong>")
                lines.append(
                    f"<p>Changed: {_safe(', '.join(fd.attributes_changed))}</p>"
                )

                if fd.values:
                    lines.append("<table style='margin-top: 8px;'>")
                    lines.append("<tr><th>Attribute</th>")
                    for profile_id in self.comparison.profiles:
                        lines.append(f"<th>{_safe(profile_id)}</th>")
                    lines.append("</tr>")

                    for attr, values in fd.values.items():
                        lines.append(f"<tr><td>{_safe(attr)}</td>")
                        for profile_id in self.comparison.profiles:
                            val = values.get(profile_id, "-")
                            lines.append(f"<td>{_safe(val)}</td>")
                        lines.append("</tr>")

                    lines.append("</table>")

                lines.append("</div>")

    def _add_html_field_details(self: Self, lines: list[str]) -> None:
        """Add HTML field details section.

        Args:
            lines: List of lines to append to.
        """
        for ed in self.comparison.entity_diffs:
            if not ed.field_diffs:
                continue

            lines.append(f"<h3>{_safe(ed.entity_name)}</h3>")
            lines.append("<table>")
            lines.append("<tr>")
            lines.append("<th>Field</th>")
            lines.append("<th>Status</th>")
            for profile_id in self.comparison.profiles:
                lines.append(f"<th>{_safe(profile_id)} Type</th>")
            lines.append("<th>Changes</th>")
            lines.append("</tr>")

            for fd in ed.field_diffs:
                css_class = fd.diff_type.value
                lines.append(f"<tr class='{css_class}'>")
                lines.append(f"<td>{_safe(fd.field_name)}</td>")
                lines.append(
                    f"<td><span class='badge {css_class}'>{fd.diff_type.value}</span></td>"
                )

                for profile_id in self.comparison.profiles:
                    spec = fd.profiles.get(profile_id)
                    type_val = spec.type.value if spec else "-"
                    lines.append(f"<td>{_safe(type_val)}</td>")

                lines.append(
                    f"<td>{_safe(', '.join(fd.attributes_changed) or '-')}</td>"
                )
                lines.append("</tr>")

            lines.append("</table>")
