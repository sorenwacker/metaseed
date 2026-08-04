"""Regression tests for issue #139 F3/A1.

F3: a rule-level ``pattern`` on a ``uri`` field is enforced by the engine (a
Pydantic pattern can't be applied to ``AnyUrl``, so it would otherwise silently
do nothing). A1: validation rules must not name a field the entity does not have.
"""

from __future__ import annotations

from metaseed.specs.loader import SpecLoader
from metaseed.validators.engine import create_engine_for_entity


def test_uri_pattern_rule_is_enforced() -> None:
    # the SEEK profile's seek_id_format (uri field, pattern ^https?://.*$) applies to all.
    engine = create_engine_for_entity("Project", version="1.0", profile="seek")
    assert any("seek_id" in str(e) for e in engine.validate({"seek_id": "not-a-url"}))
    assert not any(
        "seek_id" in str(e)
        for e in engine.validate({"seek_id": "https://seek.example.org/1"})
    )


def test_absent_uri_value_passes_for_authoring() -> None:
    # Accessions/ids are assigned later; an entity being authored (no value) must
    # not trip the pattern.
    engine = create_engine_for_entity("Project", version="1.0", profile="seek")
    assert not any("seek_id" in str(e) for e in engine.validate({}))


def _rule(profile: str, version: str, name: str):
    spec = SpecLoader(profile=profile).load_profile(version, profile)
    return next(r for r in spec.validation_rules if r.name == name)


def test_miappe_range_rules_only_target_entities_with_the_field() -> None:
    for version in ("1.1", "1.2"):
        rule = _rule("miappe", version, "latitude_range")
        # BiologicalMaterial uses biological_material_latitude, not `latitude`.
        assert "BiologicalMaterial" not in rule.applies_to
        assert set(rule.applies_to) == {"Study", "MaterialSource"}


def test_miappe_date_rules_only_target_investigation() -> None:
    for version in ("1.1", "1.2"):
        rule = _rule("miappe", version, "submission_date_format")
        assert rule.applies_to == ["Investigation"]  # Study has no submission_date


def test_isa_has_no_orcid_rule_for_a_missing_field() -> None:
    spec = SpecLoader(profile="isa").load_profile("1.0", "isa")
    assert not any(r.name == "orcid_format" for r in spec.validation_rules)
    assert "orcid" not in {f.name for f in spec.entities["Person"].fields}
