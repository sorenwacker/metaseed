"""A self-referencing field must not close a loop (#250).

Self-references shipped in 0.34.0 and Darwin Core declares two. Both loop
shapes pass an existence check, because the target EXISTS in both: a record
naming itself, and a cycle (A.parent = B, B.parent = A). Walking up from
either never terminates, which is what a tree render or an ancestry export
does with it. The rules are named and classified here — `reference_self` and
`reference_cycle`, both blocking value errors — so every consumer gets the
same behaviour through the same channel as `reference_integrity`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from metaseed.validators.base import Kind
from metaseed.validators.dataset import DatasetValidator


class _NoService:
    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return False


@pytest.fixture
def profile_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "metaseed" / "specs" / "loopy" / "1.0"
    directory.mkdir(parents=True)
    (directory / "profile.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "loopy",
                "version": "1.0",
                "spec_version": "0.6",
                "root_entity": "Study",
                "entities": {
                    "Study": {
                        "fields": [
                            {"name": "title", "type": "string", "required": True},
                            {"name": "events", "type": "list", "items": "Event"},
                        ]
                    },
                    "Event": {
                        "fields": [
                            {
                                "name": "event_id",
                                "type": "string",
                                "required": True,
                                "is_identifier": True,
                            },
                            {
                                "name": "parent_event_id",
                                "type": "string",
                                "reference": "Event.event_id",
                            },
                        ]
                    },
                },
            }
        )
    )
    return directory


def _validate(tmp_path: Path, events: list[dict]) -> list:
    dataset = tmp_path / "data"
    dataset.mkdir(exist_ok=True)
    (dataset / "study.yaml").write_text(
        yaml.safe_dump({"title": "T", "events": events})
    )
    validator = DatasetValidator("loopy", "1.0", _NoService())
    return validator.validate_file(dataset / "study.yaml").errors


def test_a_record_naming_itself_is_reference_self(
    profile_dir: Path, tmp_path: Path
) -> None:
    errors = _validate(tmp_path, [{"event_id": "E-1", "parent_event_id": "E-1"}])

    hits = [e for e in errors if e.rule == "reference_self"]
    assert hits, [(e.rule, e.message) for e in errors]
    assert all(e.kind is Kind.VALUE for e in hits)
    assert "E-1" in hits[0].message


def test_a_two_record_cycle_is_reference_cycle_on_each_member(
    profile_dir: Path, tmp_path: Path
) -> None:
    errors = _validate(
        tmp_path,
        [
            {"event_id": "A", "parent_event_id": "B"},
            {"event_id": "B", "parent_event_id": "A"},
        ],
    )

    hits = [e for e in errors if e.rule == "reference_cycle"]
    assert len(hits) == 2, [(e.rule, e.message) for e in errors]
    assert all(e.kind is Kind.VALUE for e in hits)


def test_a_clean_chain_raises_neither(profile_dir: Path, tmp_path: Path) -> None:
    errors = _validate(
        tmp_path,
        [
            {"event_id": "ROOT"},
            {"event_id": "MID", "parent_event_id": "ROOT"},
            {"event_id": "LEAF", "parent_event_id": "MID"},
        ],
    )

    loops = [e for e in errors if e.rule in ("reference_self", "reference_cycle")]
    assert not loops, [(e.rule, e.message) for e in loops]


def test_a_preexisting_cycle_does_not_blame_a_clean_record(
    profile_dir: Path, tmp_path: Path
) -> None:
    """The clean record hangs off a cycle it did not create; the cycle is
    reported against its members, not against the newcomer."""
    errors = _validate(
        tmp_path,
        [
            {"event_id": "A", "parent_event_id": "B"},
            {"event_id": "B", "parent_event_id": "A"},
            {"event_id": "CLEAN", "parent_event_id": "A"},
        ],
    )

    cycle_messages = " ".join(e.message for e in errors if e.rule == "reference_cycle")
    assert "CLEAN" not in cycle_messages
    assert len([e for e in errors if e.rule == "reference_cycle"]) == 2
