"""Regression tests: rule-level constraints (enum/pattern/range) are enforced.

Guards the critical bug where a constraint declared on a ``validation_rule`` (not
on the field's own ``constraints``) was silently dropped, so out-of-range and
out-of-vocabulary values validated as clean. The fix mirrors rule constraints onto
the field at load time (``specs.loader._merge_rule_constraints_into_fields``), so
the generated Pydantic model enforces them. Before the fix every assertion below
that expects an error returned zero errors.
"""

from __future__ import annotations

from metaseed.specs.loader import SpecLoader
from metaseed.validators.api import validate_entity


def _miappe(data: dict, entity: str) -> list:
    return validate_entity(data, entity, version="1.2", profile="miappe")


class TestRuleRangeEnforced:
    def test_altitude_above_max_rejected(self):
        # altitude_range rule: -500..9000, declared on the rule not the field.
        errs = _miappe(
            {
                "unique_id": "S1",
                "title": "t",
                "investigation_id": "INV1",
                "altitude": 999999.0,
            },
            "Study",
        )
        assert errs, "altitude 999999 must be rejected"

    def test_altitude_below_min_rejected(self):
        errs = _miappe(
            {
                "unique_id": "S2",
                "title": "t",
                "investigation_id": "INV1",
                "altitude": -9999.0,
            },
            "Study",
        )
        assert errs

    def test_altitude_in_range_passes(self):
        errs = _miappe(
            {
                "unique_id": "S3",
                "title": "t",
                "investigation_id": "INV1",
                "altitude": 1200.0,
            },
            "Study",
        )
        assert errs == []


class TestRuleEnumEnforced:
    def test_bad_enum_rejected(self):
        errs = _miappe(
            {"unique_id": "OU1", "study_id": "S1", "observation_unit_type": "GARBAGE"},
            "ObservationUnit",
        )
        assert errs, "observation_unit_type 'GARBAGE' must be rejected"

    def test_valid_enum_passes(self):
        errs = _miappe(
            {"unique_id": "OU2", "study_id": "S1", "observation_unit_type": "plant"},
            "ObservationUnit",
        )
        assert errs == []

    def test_enum_enforced_in_another_profile(self):
        # Breadth: ENA library_strategy enum is declared on a rule, not the field.
        errs = validate_entity(
            {"library_strategy": "NOTREAL"}, "Experiment", version="1.0", profile="ena"
        )
        assert any("library_strategy" in e.field or "WGS" in e.message for e in errs), (
            "ENA library_strategy enum must be enforced"
        )


class TestFieldConstraintStillWins:
    def test_field_level_constraint_not_clobbered(self):
        # latitude declares its -90..90 range on the FIELD; the loader merge must
        # leave it intact (field-level wins on conflict).
        errs = _miappe(
            {
                "unique_id": "S4",
                "title": "t",
                "investigation_id": "INV1",
                "latitude": 500.0,
                "longitude": 10.0,
            },
            "Study",
        )
        assert any("90" in e.message or "latitude" in e.field for e in errs)


class TestLoaderMerge:
    def test_rule_constraints_copied_onto_field(self):
        study = SpecLoader(profile="miappe").load_entity("Study", "1.2")
        altitude = next(f for f in study.fields if f.name == "altitude")
        assert altitude.constraints is not None
        assert altitude.constraints.minimum == -500
        assert altitude.constraints.maximum == 9000

    def test_field_own_constraint_preserved(self):
        study = SpecLoader(profile="miappe").load_entity("Study", "1.2")
        latitude = next(f for f in study.fields if f.name == "latitude")
        assert latitude.constraints is not None
        # latitude's own field-level range is unchanged.
        assert latitude.constraints.minimum == -90
        assert latitude.constraints.maximum == 90
