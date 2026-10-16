"""A rule the compared profiles define differently is shown for each profile.

The comparison recorded `validation_rule_diffs`, but nothing read it: no
report had a rule section, the sidebar listed only the base profile's rules,
and the entity panel kept the first profile's version of a same-named rule.
Two profiles whose `id_format` rules set `^A` and `^B` showed only `^A`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from metaseed.specs.merge.comparator import SpecComparator
from metaseed.specs.merge.models import ComparisonResult
from metaseed.specs.merge.reports import (
    CSVReportGenerator,
    HTMLReportGenerator,
    MarkdownReportGenerator,
)
from metaseed.specs.merge.visualizer import DiffVisualizer
from metaseed.specs.schema import ProfileSpec

PANEL_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "metaseed"
    / "ui"
    / "static"
    / "js"
    / "explore-panel.js"
)


def _profile(name: str, rules: list[dict[str, Any]]) -> ProfileSpec:
    return ProfileSpec.model_validate(
        {
            "version": "1.0",
            "name": name,
            "root_entity": "Study",
            "entities": {
                "Study": {"fields": [{"name": "identifier", "type": "string"}]}
            },
            "validation_rules": rules,
        }
    )


def _id_rule(pattern: str) -> dict[str, Any]:
    return {
        "name": "id_format",
        "type": "pattern",
        "applies_to": ["Study"],
        "field": "identifier",
        "pattern": pattern,
    }


def _compare() -> ComparisonResult:
    specs = {
        "a": _profile("a", [_id_rule("^A")]),
        "b": _profile(
            "b",
            [
                _id_rule("^B"),
                {
                    "name": "b_only",
                    "type": "required",
                    "applies_to": "all",
                    "field": "identifier",
                },
            ],
        ),
    }

    class _Loader:
        def load_profile(self, version=None, profile=None, **_kw):
            return specs[profile]

        def list_versions(self, *_a, **_k):
            return ["1.0"]

    return SpecComparator(loader=_Loader()).compare([("a", "1.0"), ("b", "1.0")])  # type: ignore[arg-type]


def test_the_entity_carries_each_profiles_version_of_a_differing_rule() -> None:
    graph = DiffVisualizer().build_diff_graph(_compare())
    (node,) = [n for n in graph["nodes"] if n["data"].get("name") == "Study"]
    rule = next(r for r in node["data"]["rules"] if r["name"] == "id_format")

    assert [(v["profile"], v["rule"]["pattern"]) for v in rule["variants"]] == [
        ("a/1.0", "^A"),
        ("b/1.0", "^B"),
    ]


def test_a_rule_one_profile_lacks_has_an_empty_variant() -> None:
    graph = DiffVisualizer().build_diff_graph(_compare())
    by_name = {d["name"]: d for d in graph["rule_diffs"]}

    assert set(by_name) == {"id_format", "b_only"}
    assert [v["rule"] is None for v in by_name["b_only"]["variants"]] == [
        True,
        False,
    ]


def test_an_agreeing_rule_carries_no_variants() -> None:
    specs = _compare()
    specs.validation_rule_diffs.pop("id_format")
    graph = DiffVisualizer().build_diff_graph(specs)
    (node,) = [n for n in graph["nodes"] if n["data"].get("name") == "Study"]
    rule = next(r for r in node["data"]["rules"] if r["name"] == "id_format")

    assert "variants" not in rule


@pytest.mark.parametrize(
    "generator",
    [MarkdownReportGenerator, HTMLReportGenerator, CSVReportGenerator],
)
def test_every_report_lists_each_profiles_version(generator: type) -> None:
    report = generator(_compare()).generate()

    assert "id_format" in report and "b_only" in report
    assert "^A" in report and "^B" in report


def test_a_pipe_in_a_pattern_does_not_split_the_markdown_row() -> None:
    result = _compare()
    result.validation_rule_diffs["id_format"]["a/1.0"].pattern = "^(A|C)"  # type: ignore[union-attr]
    report = MarkdownReportGenerator(result).generate()
    (row,) = [line for line in report.splitlines() if line.startswith("| id_format")]

    assert "^(A\\|C)" in row


def test_a_hostile_rule_is_escaped_in_the_html_report() -> None:
    result = _compare()
    result.validation_rule_diffs["id_format"]["a/1.0"].pattern = "<script>"  # type: ignore[union-attr]

    assert "<script>" not in HTMLReportGenerator(result).generate()


def _render(expression: str, payload: Any) -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = (
        PANEL_SCRIPT.read_text()
        + f"\nconst payload = {json.dumps(payload)};\n"
        + f"process.stdout.write({expression});\n"
    )
    return subprocess.run(
        [node, "-e", script], capture_output=True, text=True, check=True
    ).stdout


def test_the_panel_draws_both_versions_side_by_side() -> None:
    graph = DiffVisualizer().build_diff_graph(_compare())
    (node,) = [n for n in graph["nodes"] if n["data"].get("name") == "Study"]
    html = _render("payload.map(renderRuleEntry).join('')", node["data"]["rules"])

    assert "^A" in html and "^B" in html
    assert "a/1.0" in html and "b/1.0" in html
    assert "not defined" in html, "b_only is missing from profile a"


def test_the_sidebar_lists_a_rule_the_base_profile_lacks() -> None:
    graph = DiffVisualizer().build_diff_graph(_compare())
    html = _render(
        "sidebarRuleEntries(payload.rules, 'a/1.0', payload.rule_diffs)"
        ".map(renderRuleEntry).join('')",
        graph,
    )

    assert "b_only" in html
    assert "^A" in html and "^B" in html
