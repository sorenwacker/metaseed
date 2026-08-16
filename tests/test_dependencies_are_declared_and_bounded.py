"""Dependencies are declared where they are imported, and bounded (260816).

Two project rules with no enforcement, so both had drifted:

- "Declare every package the code imports directly in pyproject; never rely on
  it arriving transitively." `httpx` is imported at module level by the MCP
  ontology tools — reached at import time — but appeared only under extras. It
  arrived through `mcp`, which pins `httpx>=0.27.1,<1.0.0`; the day `mcp` drops
  or vendors it, a base install cannot import its own MCP server.
- "Bound dependencies below the next major version." Only `mcp` was bounded.
  A lockfile-based suite stays green while a fresh install resolves pydantic 3
  and behaves differently — the exact failure the rule exists to prevent, and
  the one that already happened once with `mcp` 2.0 removing `mcp.server.fastmcp`.

The bound is asserted on runtime dependencies and the extras that ship with the
package. Dev-only tooling is exempt: it never reaches a user's environment.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
#: Extras that exist for developing metaseed, not for running it.
DEV_ONLY_EXTRAS = frozenset({"dev", "docs"})

#: What caps a requirement from above: `<`, an exact pin, or a compatible
#: release. `>=2.0` alone is not a bound — an early version of this test looked
#: for "=" and passed on every requirement, which is why it says so here.
_UPPER_BOUND = re.compile(r"(<|==|~=)")


def _config() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def _shipped_requirements() -> dict[str, list[str]]:
    project = _config()["project"]
    groups = {"dependencies": list(project.get("dependencies", []))}
    for extra, requirements in project.get("optional-dependencies", {}).items():
        if extra not in DEV_ONLY_EXTRAS:
            groups[extra] = list(requirements)
    return groups


def test_every_shipped_requirement_is_bounded_below_the_next_major() -> None:
    unbounded = {
        group: [r for r in requirements if not _UPPER_BOUND.search(r)]
        for group, requirements in _shipped_requirements().items()
    }
    offenders = {group: rs for group, rs in unbounded.items() if rs}

    assert not offenders, (
        "requirements with no upper bound: "
        f"{offenders}. An unbounded minimum means a future major release "
        "breaks fresh installs while lockfile-based tests stay green."
    )


def test_httpx_is_declared_where_it_is_imported() -> None:
    """It is imported at module level by code the MCP server imports."""
    names = {
        re.split(r"[<>=!\[]", requirement)[0].strip()
        for requirement in _config()["project"]["dependencies"]
    }

    assert "httpx" in names, (
        "httpx is imported by agent/mcp/tools/ontology.py at module level but "
        "reaches the environment only through mcp's own pin"
    )
