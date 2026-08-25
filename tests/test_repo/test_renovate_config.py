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
