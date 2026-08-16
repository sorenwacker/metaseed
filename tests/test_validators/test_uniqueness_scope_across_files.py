"""Parent scope is per parent, including across files (260816 review).

`validate_directory` shares one `seen` set across every file so a global-scope
rule can catch cross-file duplicates. But the parent-scope key was built from
the file-relative path alone, so `studies[0].observation_units` in one file and
the same path in another produced the same key: two children under genuinely
different parents were reported as duplicates of each other.

Measured before the fix, on two MIAPPE investigations each carrying its own
OU-1 and OU-2: 2 false "is not unique ... within parent scope" errors. Only the
directory path was affected — single-file validation starts from a fresh set.

The change loosens: records reported invalid today are reported valid. Nothing
that passes now starts failing.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from metaseed.validators.dataset import DatasetValidator


def _investigation(n: int, unit_ids: list[str]) -> dict:
    return {
        "unique_id": f"INV-{n}",
        "title": f"I{n}",
        "description": "d",
        "submission_date": "2024-01-01",
        "public_release_date": "2024-02-01",
        "license": "CC-BY",
        "studies": [
            {
                "unique_id": f"STU-{n}",
                "title": "S",
                "investigation_id": f"INV-{n}",
                "observation_units": [
                    {"unique_id": u, "study_id": f"STU-{n}"} for u in unit_ids
                ],
            }
        ],
    }


def _write(directory: Path, files: dict[str, dict]) -> None:
    for name, document in files.items():
        (directory / name).write_text(yaml.safe_dump(document))


def _duplicate_errors(result) -> list[str]:
    return [
        e.message for e in result.errors if "not unique" in (e.message or "").lower()
    ]


def test_children_of_different_parents_are_not_duplicates(tmp_path: Path) -> None:
    """The finding: each investigation's own OU-1 collided with the other's."""
    _write(
        tmp_path,
        {
            "inv1.yaml": _investigation(1, ["OU-1", "OU-2"]),
            "inv2.yaml": _investigation(2, ["OU-1", "OU-2"]),
        },
    )

    result = DatasetValidator(profile="miappe", version="1.2").validate_directory(
        tmp_path
    )

    assert _duplicate_errors(result) == []


def test_a_duplicate_under_one_parent_is_still_reported(tmp_path: Path) -> None:
    """The rule must keep doing its job within a parent."""
    _write(tmp_path, {"inv1.yaml": _investigation(1, ["OU-1", "OU-1"])})

    result = DatasetValidator(profile="miappe", version="1.2").validate_directory(
        tmp_path
    )

    assert len(_duplicate_errors(result)) == 1, _duplicate_errors(result)


def test_a_global_rule_still_sees_across_files(tmp_path: Path) -> None:
    """Why `seen` is shared at all: global scope spans the whole directory.

    No shipped profile declares global scope today, so the mechanism is pinned
    here rather than left to erode unnoticed.
    """
    _write(
        tmp_path,
        {
            "inv1.yaml": _investigation(1, ["OU-1"]),
            "inv2.yaml": _investigation(2, ["OU-1"]),
        },
    )
    validator = DatasetValidator(profile="miappe", version="1.2")
    # `_UniquenessRuleDef` is a NamedTuple, so a global-scope variant is built
    # rather than assigned. No shipped profile declares one.
    validator._uniqueness.rules = [
        rule._replace(scope="global") for rule in validator._uniqueness.rules
    ]

    result = validator.validate_directory(tmp_path)

    assert len(_duplicate_errors(result)) == 1, _duplicate_errors(result)
