"""A profile's own text must not become markup in the report (260816 review).

`HTMLReportGenerator` interpolated every value straight into the page —
entity names, field names, descriptions, patterns, examples, profile ids — and
the comparison report is served as `text/html` from `/explore/report/...`.
Profiles are not all first-party: a user specs directory or a hub-authored
profile can carry `<script>`, and comparing one would run it in the reader's
browser.

The sibling HTML emitter (`ui/routes/dcat.py`) escapes every interpolation, so
this was also a divergence from the pattern already established here.
"""

from __future__ import annotations

from metaseed.specs.merge.models import ComparisonResult, DiffType, EntityDiff
from metaseed.specs.merge.reports import HTMLReportGenerator

HOSTILE = '<script>alert("xss")</script>'


def _report_with(entity_name: str) -> str:
    result = ComparisonResult(
        profiles=["a", "b"],
        entity_diffs=[
            EntityDiff(
                entity_name=entity_name,
                diff_type=DiffType.ADDED,
                profiles={"a": True, "b": False},
            )
        ],
    )
    return HTMLReportGenerator(result).generate()


def test_a_hostile_entity_name_is_escaped() -> None:
    html = _report_with(HOSTILE)

    assert "<script>" not in html, "profile text reached the page as markup"
    assert "&lt;script&gt;" in html


def test_the_name_is_still_readable() -> None:
    """Escaping must not lose the content, only its power to be markup."""
    html = _report_with("Sample")

    assert "Sample" in html
