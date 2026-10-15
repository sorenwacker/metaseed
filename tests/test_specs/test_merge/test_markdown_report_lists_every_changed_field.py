"""The Markdown report lists every changed field, removed ones included.

Its field section kept only MODIFIED and ADDED fields, so a field the compared
profiles dropped appeared in the CSV and HTML reports but nowhere in the
Markdown one.
"""

from __future__ import annotations

from metaseed.specs.merge import compare
from metaseed.specs.merge.models import DiffType
from metaseed.specs.merge.reports import MarkdownReportGenerator


def test_every_non_conflicting_changed_field_is_listed() -> None:
    comparison = compare([("miappe", "1.1"), ("isa", "1.0")])
    report = MarkdownReportGenerator(comparison).generate()
    section = report.split("## Changed Fields", 1)[1]

    changed = [
        (ed.entity_name, fd.field_name)
        for ed in comparison.entity_diffs
        for fd in ed.field_diffs
        if fd.diff_type not in (DiffType.UNCHANGED, DiffType.CONFLICT)
    ]
    assert any(
        fd.diff_type == DiffType.REMOVED
        for ed in comparison.entity_diffs
        for fd in ed.field_diffs
    ), "the fixture comparison must contain a removed field"
    for entity, field in changed:
        assert f"| {field} |" in section, f"{entity}.{field} missing from the report"
