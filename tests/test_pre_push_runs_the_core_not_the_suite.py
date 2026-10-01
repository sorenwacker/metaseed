"""A push runs the fast core before it leaves the machine; CI runs the suite.

The pre-push hook ran the full fifteen-minute suite on every push, which the
pull request's CI then ran again (#277). People reached for ``--no-verify``,
which disables every hook, including the fast ones worth keeping. The hook now
runs ``scripts/pre_push_tests.py``: the core subset by default (about six
seconds), the full suite for a tag push, where nothing downstream checks, or
when ``METASEED_PUSH_FULL=1`` asks for it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pre_push_tests.py"


def _script():
    spec = importlib.util.spec_from_file_location("pre_push_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _pre_push_pytest_hook() -> dict:
    config = yaml.safe_load(
        (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook.get("id") == "pytest":
                return hook
    raise AssertionError("no pytest hook in .pre-commit-config.yaml")


def test_the_hook_runs_the_script_not_the_whole_suite() -> None:
    hook = _pre_push_pytest_hook()
    assert "pre-push" in hook.get("stages", [])
    assert "scripts/pre_push_tests.py" in hook["entry"], hook["entry"]


def test_a_branch_push_runs_the_core_subset() -> None:
    script = _script()
    assert (
        script.scope({"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/feature"})
        == script.CORE_SUBSET
    )
    assert script.scope({}) == script.CORE_SUBSET


def test_a_tag_push_runs_the_full_suite() -> None:
    script = _script()
    assert (
        script.scope({"PRE_COMMIT_REMOTE_BRANCH": "refs/tags/v1.0.0"})
        == script.FULL_SUITE
    )


def test_the_full_suite_can_be_asked_for() -> None:
    script = _script()
    assert script.scope({"METASEED_PUSH_FULL": "1"}) == script.FULL_SUITE


def test_every_core_path_exists() -> None:
    missing = [p for p in _script().CORE if not (ROOT / p).exists()]
    assert not missing, missing


def test_the_core_excludes_what_ci_excludes() -> None:
    """Local must match CI: the subset carries the same marker exclusions."""
    script = _script()
    for excluded in ("not network", "not selenium"):
        assert excluded in script.MARKERS
    assert "-m" in script.command(script.FULL_SUITE)
