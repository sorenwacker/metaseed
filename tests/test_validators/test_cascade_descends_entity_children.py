"""`validate(cascade=True)` must descend entity-typed (singly nested) children.

The cascade recursed only into list-typed fields. `FieldType.ENTITY` holds a
single nested child dict — Darwin Core nests both its Event and its Organism
this way — and such a child was never visited: its required fields went
unchecked, and the raw dict was passed into the parent's Pydantic model
instead, producing a misleading "extra inputs" error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def profile_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "metaseed" / "specs" / "singly" / "1.0"
    directory.mkdir(parents=True)
    (directory / "profile.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "singly",
                "version": "1.0",
                "root_entity": "Occurrence",
                "entities": {
                    "Occurrence": {
                        "fields": [
                            {"name": "title", "type": "string", "required": True},
                            {"name": "event", "type": "entity", "items": "Event"},
                        ]
                    },
                    "Event": {
                        "fields": [
                            {"name": "event_id", "type": "string", "required": True},
                        ]
                    },
                },
            }
        )
    )
    return directory


def test_the_cascade_reports_the_single_childs_missing_field(
    profile_dir: Path,
) -> None:
    from metaseed.validators.api import validate

    errors = validate(
        {"title": "T", "event": {}},
        entity="Occurrence",
        version="1.0",
        profile="singly",
    )

    assert any(e.rule == "required_fields" and "event" in e.field for e in errors), (
        f"missing event_id not reported: {[(e.field, e.rule, e.message) for e in errors]}"
    )


def test_the_child_dict_is_not_fed_to_the_parents_model(profile_dir: Path) -> None:
    from metaseed.validators.api import validate

    errors = validate(
        {"title": "T", "event": {"event_id": "E1"}},
        entity="Occurrence",
        version="1.0",
        profile="singly",
    )

    assert not any("extra" in e.message.lower() for e in errors), [
        (e.field, e.message) for e in errors
    ]
