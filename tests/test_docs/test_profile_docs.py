"""Docs CI gate: every profile page must match its spec, and its examples run.

This guards against the rot found in issue #139 (F1/F2/A6): profile pages that
name entities/fields which no longer exist, and code examples that raise. For
each `docs/profiles/<p>.md` it:

* asserts every entity named in the page's mermaid ``erDiagram`` exists in the
  loaded ``ProfileSpec``, and every field listed under an entity is a real field
  (matched by ``name`` or ``codename``);
* asserts **completeness** — every spec entity is mentioned on the page;
* executes each fenced ``python`` block and asserts it does not raise.

Hermetic: loads specs through ``SpecLoader`` and runs the doc examples in-process;
no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from metaseed.specs.loader import SpecLoader

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_PROFILES = _DOCS / "profiles"

# doc filename -> (profile name, version the page documents)
PROFILE_DOCS: dict[str, tuple[str, str]] = {
    "darwin-core.md": ("darwin-core", "1.0"),
    "dissco.md": ("dissco", "0.4"),
    "ena.md": ("ena", "1.0"),
    "isa.md": ("isa", "1.0"),
    "jerm.md": ("jerm", "1.0"),
    "metabolights.md": ("metabolights", "1.0"),
    "miappe.md": ("miappe", "1.2"),  # library default; page targets 1.2
    "miappe-htp.md": ("miappe-htp", "1.0"),
    "pride.md": ("pride", "1.0"),
}

_FENCE = re.compile(r"```(\w+)\n(.*?)```", re.DOTALL)
_ENTITY_OPEN = re.compile(r"^([A-Za-z]\w*)\s*\{")
_FIELD = re.compile(r"^\S+\s+([A-Za-z]\w*)")
_RELATION = re.compile(r"^([A-Za-z]\w*)\s+\S+\s+([A-Za-z]\w*)\s*:")


def _blocks(text: str, lang: str) -> list[str]:
    return [body for tag, body in _FENCE.findall(text) if tag == lang]


def _parse_erd(text: str) -> dict[str, set[str]]:
    """Entity -> field names, parsed from every ``erDiagram`` block on the page."""
    entities: dict[str, set[str]] = {}
    for block in _blocks(text, "mermaid"):
        if "erDiagram" not in block:
            continue
        current: str | None = None
        for raw in block.splitlines():
            line = raw.strip()
            if not line or line == "erDiagram":
                continue
            opened = _ENTITY_OPEN.match(line)
            if opened:
                current = opened.group(1)
                entities.setdefault(current, set())
                continue
            if line == "}":
                current = None
                continue
            if current is not None:
                field = _FIELD.match(line)
                if field:
                    entities[current].add(field.group(1))
                continue
            relation = _RELATION.match(line)
            if relation:
                entities.setdefault(relation.group(1), set())
                entities.setdefault(relation.group(2), set())
    return entities


def _doc_ids() -> list[str]:
    return sorted(PROFILE_DOCS)


@pytest.fixture(params=_doc_ids())
def profile_doc(request: pytest.FixtureRequest) -> tuple[str, str, str]:
    filename = request.param
    profile, version = PROFILE_DOCS[filename]
    text = (_PROFILES / filename).read_text()
    return text, profile, version


def test_erd_entities_and_fields_exist(profile_doc: tuple[str, str, str]) -> None:
    text, profile, version = profile_doc
    spec = SpecLoader(profile=profile).load_profile(version, profile)
    erd = _parse_erd(text)
    assert erd, f"{profile}: no erDiagram entities parsed from the page"

    unknown_entities = [name for name in erd if name not in spec.entities]
    assert not unknown_entities, (
        f"{profile}: page ERD names entities absent from the spec: {unknown_entities}"
    )

    for entity_name, fields in erd.items():
        valid = {f.name for f in spec.entities[entity_name].fields}
        valid |= {f.codename for f in spec.entities[entity_name].fields if f.codename}
        unknown = sorted(fields - valid)
        assert not unknown, (
            f"{profile}.{entity_name}: page ERD lists fields absent from the "
            f"spec: {unknown}"
        )


def test_every_spec_entity_is_documented(profile_doc: tuple[str, str, str]) -> None:
    text, profile, version = profile_doc
    spec = SpecLoader(profile=profile).load_profile(version, profile)
    missing = [
        name for name in spec.entities if not re.search(rf"\b{re.escape(name)}\b", text)
    ]
    assert not missing, (
        f"{profile}: spec entities never mentioned on the page: {missing}"
    )


def test_python_examples_execute(profile_doc: tuple[str, str, str]) -> None:
    text, profile, _ = profile_doc
    blocks = _blocks(text, "python")
    for i, block in enumerate(blocks):
        try:
            exec(compile(block, f"<{profile}.md block {i}>", "exec"), {})  # noqa: S102
        except Exception as exc:
            pytest.fail(f"{profile}.md python block {i} raised: {exc!r}\n{block}")
