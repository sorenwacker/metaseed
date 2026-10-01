"""The fresh-install smoke test runs before release day, not only on it (#286).

``fresh-install-smoke`` builds the wheel, installs it into a clean environment
with a fresh dependency resolution and runs the entry points. It caught a
widened ``mcp`` bound that every locked test run had passed, but only when
v0.50.0 was tagged: the tag then existed with no release behind it. The job is
now one reusable workflow, run by the release and also weekly and on every pull
request that changes ``pyproject.toml`` or ``uv.lock``, so a broken bound is
found on the pull request that introduces it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
REUSABLE = "./.github/workflows/fresh-install-smoke.yml"


def _load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML reads the bare key ``on`` as boolean True.
    if True in data:
        data["on"] = data.pop(True)
    return data


def test_the_smoke_is_one_reusable_workflow() -> None:
    smoke = _load("fresh-install-smoke.yml")
    assert "workflow_call" in smoke["on"]
    steps = " ".join(
        step.get("run", "") for job in smoke["jobs"].values() for step in job["steps"]
    )
    for probe in ("uv build", "metaseed --help", "metaseed ui", "create_server()"):
        assert probe in steps, f"the smoke no longer runs {probe!r}"


def test_the_release_still_gates_publishing_on_it() -> None:
    release = _load("release.yml")
    assert release["jobs"]["fresh-install-smoke"]["uses"] == REUSABLE
    assert "fresh-install-smoke" in release["jobs"]["publish"]["needs"]


def test_it_runs_weekly_and_on_dependency_changes() -> None:
    scheduled = _load("smoke.yml")
    triggers = scheduled["on"]
    assert triggers.get("schedule"), "no weekly run"
    paths = triggers["pull_request"]["paths"]
    assert "pyproject.toml" in paths and "uv.lock" in paths
    assert "workflow_dispatch" in triggers
    assert any(job.get("uses") == REUSABLE for job in scheduled["jobs"].values())
