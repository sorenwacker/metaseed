"""The dependency-update configuration is Renovate on the best-practices preset.

Dependabot cannot update ``uv.lock``, so its PRs left the lockfile -- what CI
and installs actually use -- untouched. Renovate's ``uv`` manager regenerates
it, and ``config:best-practices`` pins Actions to digests and waits out a
release before proposing it. This gate keeps the config parseable and on that
preset, and keeps a Dependabot config from creeping back beside it.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_renovate_extends_best_practices():
    config = json.loads((ROOT / "renovate.json").read_text())
    assert "config:best-practices" in config["extends"]
    assert config.get("lockFileMaintenance", {}).get("enabled") is True


def test_there_is_no_dependabot_config_beside_it():
    assert not (ROOT / ".github" / "dependabot.yml").exists()


def test_renovate_runs_from_this_repositorys_own_workflow():
    """The hosted app never ran here; a workflow we can see does the job.

    It reads the same config, runs on a schedule and on demand, pins the
    action to a commit, and uses a real token: a pull request opened with
    GITHUB_TOKEN triggers no other workflow, so the CI gate would never report
    on an update and auto-merge could never fire.
    """
    workflow = (ROOT / ".github" / "workflows" / "renovate.yml").read_text()
    assert "renovatebot/github-action@" in workflow
    assert "configurationFile: renovate.json" in workflow
    assert "schedule:" in workflow and "workflow_dispatch:" in workflow
    assert "token: ${{ secrets.RENOVATE_TOKEN }}" in workflow
    assert "GITHUB_TOKEN" not in workflow.split("token: ")[1].splitlines()[0]
    import re

    assert all(
        re.search(r"@[0-9a-f]{40} # v", line)
        for line in workflow.splitlines()
        if "uses:" in line
    ), "every action is pinned to a commit"
