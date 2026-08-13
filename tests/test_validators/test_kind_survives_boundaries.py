"""`ValidationError.kind` must survive every place an error is rebuilt.

The VALUE/COMPLETENESS split exists so "this is wrong" can block a write while
"this is not filled in yet" cannot. It was carried faithfully inside the
validators and then discarded at four boundaries that rebuild errors — the
cascade path, `validate_directory`'s file prefixing, the agent's
`ValidationIssue`, and the public API's schema. Everything downstream of those
points saw every error as blocking again, which un-fixes #246 for exactly the
consumers the split was built for.

One test per boundary, each constructing a record whose only error is a missing
required field (COMPLETENESS by definition) and asserting the kind arrives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from metaseed.validators.base import Kind


class _NoService:
    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return False


@pytest.fixture
def profile_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "metaseed" / "specs" / "kindly" / "1.0"
    directory.mkdir(parents=True)
    (directory / "profile.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "kindly",
                "version": "1.0",
                "root_entity": "Study",
                "entities": {
                    "Study": {
                        "fields": [
                            {"name": "title", "type": "string", "required": True},
                            {"name": "samples", "type": "list", "items": "Sample"},
                        ]
                    },
                    "Sample": {
                        "fields": [
                            {"name": "name", "type": "string", "required": True},
                        ]
                    },
                },
            }
        )
    )
    return directory


def test_the_cascade_keeps_kind_on_nested_errors(profile_dir: Path) -> None:
    """`validate_entity` rebuilds every child error to prefix its path."""
    from metaseed.validators.api import validate

    errors = validate(
        {"title": "T", "samples": [{}]},
        entity="Study",
        version="1.0",
        profile="kindly",
    )

    missing = [e for e in errors if e.rule == "required_fields"]
    assert missing, "the nested Sample is missing its required name"
    assert all(e.kind is Kind.COMPLETENESS for e in missing)


def test_validate_directory_keeps_kind(profile_dir: Path, tmp_path: Path) -> None:
    """The directory path rebuilds every error to prefix the file name."""
    from metaseed.validators.dataset import DatasetValidator

    dataset_dir = tmp_path / "data"
    dataset_dir.mkdir()
    (dataset_dir / "study.yaml").write_text(
        yaml.safe_dump({"samples": [{"name": "s"}]})
    )

    result = DatasetValidator("kindly", "1.0", _NoService()).validate_directory(
        dataset_dir
    )

    missing = [e for e in result.errors if e.rule == "required_fields"]
    assert missing, "the Study is missing its required title"
    assert all(e.kind is Kind.COMPLETENESS for e in missing)


def test_the_agents_validation_issue_keeps_kind(profile_dir: Path) -> None:
    """`ExtractionContext.validate_instance` wraps engine errors into
    ValidationIssue for the extraction report."""
    from metaseed.agent.core import ExtractionContext
    from metaseed.specs.loader import SpecLoader

    spec = SpecLoader().load_profile("1.0", "kindly")
    assert spec is not None
    context = ExtractionContext(profile=spec)
    issues = context.validate_instance({"samples": []}, "Study")

    missing = [i for i in issues if "title" in (i.field or "")]
    assert missing, "the required title is missing"
    assert all(i.kind == "completeness" for i in missing)


def test_the_public_api_schema_keeps_kind(profile_dir: Path) -> None:
    """`api.schema` is what a consumer of the library sees."""
    from metaseed.api.client import MetaseedClient

    client = MetaseedClient("kindly", "1.0")
    client.load({"entities": [{"_type": "Study", "samples": []}]})
    report = client.validate()

    issue: Any = next(
        (i for i in _iter_issues(report) if "title" in str(getattr(i, "field", ""))),
        None,
    )
    assert issue is not None, f"no title issue in {report}"
    assert getattr(issue, "kind", None) in (Kind.COMPLETENESS, "completeness")


def _iter_issues(report: Any):
    for name in ("errors", "issues"):
        found = getattr(report, name, None)
        if found:
            yield from found
