"""The README states what the package ships, and the package agrees.

A README is read before anything else and checked after everything else, so
its tables drift: a profile gains a version, a count changes, a snippet keeps
an attribute the API renamed. Each claim below is compared with the code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


def _table(heading: str) -> list[list[str]]:
    """The rows of the first markdown table under ``heading``, as cell lists."""
    text = README.read_text()
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    section = text[start : end if end > 0 else None]
    rows = []
    for line in section.splitlines():
        if line.startswith("|") and not set(line) <= {"|", "-", " "}:
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows[1:]  # drop the header


def test_the_profile_table_matches_the_shipped_profiles() -> None:
    from metaseed.specs.loader import SpecLoader

    loader = SpecLoader()
    documented: dict[str, tuple[list[str], int, int]] = {}
    for _name, key, versions, entities, fields, _domain in _table("Profiles"):
        documented[key.strip("`")] = (
            [v.strip() for v in versions.split(",")],
            int(entities),
            int(fields),
        )
    shipped: dict[str, tuple[list[str], int, int]] = {}
    for profile in loader.list_profiles():
        if loader.is_user_defined(profile):
            continue
        versions = loader.list_versions(profile)
        if not versions:
            continue
        spec = loader.load_profile(version=versions[-1], profile=profile)
        shipped[profile] = (
            versions,
            len(spec.entities),
            sum(len(e.fields) for e in spec.entities.values()),
        )
    assert set(documented) == set(shipped), (
        f"README lists {sorted(documented)}, the package ships {sorted(shipped)}"
    )
    for key, expected in shipped.items():
        assert documented[key] == expected, (
            f"{key}: README says {documented[key]}, package has {expected}"
        )


def test_the_integrations_table_names_every_adapter() -> None:
    from metaseed import adapters

    rows = {row[0] for row in _table("Integrations")}
    for info in adapters.ADAPTERS:
        assert info.name in rows, (
            f"adapter {info.name!r} is not in the README's integrations table"
        )


def test_the_python_example_runs_against_the_real_api() -> None:
    text = README.read_text()
    match = re.search(r"### Python\n\n```python\n(.*?)```", text, re.DOTALL)
    assert match, "no Python example under ### Python"
    code = match.group(1)
    ast.parse(code)
    namespace: dict[str, object] = {}
    exec(compile(code, "README.md", "exec"), namespace)  # noqa: S102 - the README's own example
    assert "result" in namespace


def test_every_relative_link_points_at_a_file() -> None:
    missing = [
        target
        for target in re.findall(r"\]\((?!http)([^)#]+)\)", README.read_text())
        if not (ROOT / target).exists()
    ]
    assert not missing, f"README links to files that do not exist: {missing}"
