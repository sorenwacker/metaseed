"""A root record whose type has more than one word gets its references checked.

_detect_entity_type lowercased ``ObservationUnit`` to ``observationunit``, but
reference fields and identifiers are keyed by snake case (``observation_unit``).
The root's own references were skipped and its identifier was registered under
a key no lookup used, so a valid reference to it was reported missing.
"""

from __future__ import annotations

import json

from metaseed.validators.dataset import DatasetValidator


def _reference_errors(result) -> list[str]:
    return [
        e.message for e in result.errors if "OU-1" in e.message or "BM-404" in e.message
    ]


def test_references_from_and_to_a_multi_word_root_type(tmp_path) -> None:
    (tmp_path / "unit.json").write_text(
        json.dumps(
            {
                "_type": "ObservationUnit",
                "unique_id": "OU-1",
                "study_id": "STU-1",
                "biological_material_id": "BM-404",
            }
        )
    )
    (tmp_path / "sample.json").write_text(
        json.dumps(
            {"_type": "Sample", "unique_id": "SMP-1", "observation_unit_id": "OU-1"}
        )
    )

    result = DatasetValidator("miappe", "1.2").validate_directory(tmp_path)

    errors = _reference_errors(result)
    assert any("BM-404" in m for m in errors), errors
    assert not any("OU-1" in m for m in errors), errors
