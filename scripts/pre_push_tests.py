"""The tests a push runs before it leaves the machine.

A push to a branch runs the fast core of the suite: the specification language,
the validators, the models and the facade, the API and the services. The pull
request's CI runs everything; paying for the full fifteen-minute suite twice
per push made people reach for ``--no-verify``, which disables every hook (#277).

A push of a release tag runs the full suite, because nothing downstream checks a
tag before it is published. ``METASEED_PUSH_FULL=1`` asks for the full suite on
any push. pre-commit names the ref being pushed in ``PRE_COMMIT_REMOTE_BRANCH``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

CORE = (
    "tests/test_specs",
    "tests/test_validators",
    "tests/test_models",
    "tests/test_facade",
    "tests/test_facade.py",
    "tests/test_facade_store.py",
    "tests/test_api",
    "tests/test_services",
    "tests/test_repositories",
    "tests/test_spec_language.py",
    "tests/test_profiles.py",
    "tests/test_examples.py",
)
MARKERS = "not network and not selenium and not ui"
FULL_SUITE = "full suite"
CORE_SUBSET = "core subset"


def scope(env: Mapping[str, str]) -> str:
    """Which tests this push runs, from the environment pre-commit provides.

    Args:
        env: The process environment.

    Returns:
        ``FULL_SUITE`` for a tag push or an explicit request, ``CORE_SUBSET``
        otherwise.
    """
    if env.get("METASEED_PUSH_FULL", "").strip() in {"1", "true", "yes"}:
        return FULL_SUITE
    if env.get("PRE_COMMIT_REMOTE_BRANCH", "").startswith("refs/tags/"):
        return FULL_SUITE
    return CORE_SUBSET


def command(which: str) -> list[str]:
    """The pytest command for a scope."""
    base = [
        sys.executable,
        "-m",
        "pytest",
        "-x",
        "-q",
        "--tb=short",
        "-n",
        "auto",
        "-m",
        MARKERS,
    ]
    return base if which == FULL_SUITE else [*base, *CORE]


def main() -> int:
    """Run the tests for this push and return pytest's exit code."""
    which = scope(os.environ)
    print(f"pre-push: running the {which} (METASEED_PUSH_FULL=1 runs everything)")
    return subprocess.call(command(which))  # noqa: S603 - our own pytest command


if __name__ == "__main__":
    raise SystemExit(main())
