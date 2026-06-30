"""Every public validation path must enforce Pydantic constraints.

Regression guard for the review's HIGH finding: validate() (the REST/CLI path)
ran only the rule engine, which does not implement pattern/range/length/enum
constraints, so constraint violations were silently reported as valid while
validate_entity() (the canonical path) caught them.
"""

from __future__ import annotations

from metaseed.validators.api import validate, validate_entity

# Study.latitude is constrained to [-90, 90] in the miappe profile.
_BAD_STUDY = {
    "unique_id": "ST1",
    "title": "S",
    "investigation_id": "I1",
    "latitude": 999,
}


def _hits_latitude(errors) -> bool:
    return any("latitude" in e.field for e in errors)


def test_validate_entity_catches_range_constraint():
    assert _hits_latitude(validate_entity(_BAD_STUDY, "Study", version="1.2"))


def test_validate_cascade_catches_range_constraint():
    assert _hits_latitude(validate(_BAD_STUDY, "study", version="1.2", cascade=True))


def test_validate_non_cascade_catches_range_constraint():
    assert _hits_latitude(validate(_BAD_STUDY, "study", version="1.2", cascade=False))


def test_valid_study_passes_all_paths():
    good = {**_BAD_STUDY, "latitude": 45}
    assert not _hits_latitude(validate_entity(good, "Study", version="1.2"))
    assert not _hits_latitude(validate(good, "study", version="1.2", cascade=True))
    assert not _hits_latitude(validate(good, "study", version="1.2", cascade=False))
