"""A field some profiles lack is still compared and merged by the strategy.

- With three or more profiles, a field missing from one of them was returned
  `MODIFIED` before any attribute was compared, so a type conflict between the
  profiles that do have it was never reported.
- An `ADDED` or `REMOVED` field was taken from the first profile having it,
  whatever strategy the caller chose.
- A manual resolution started from the first profile's spec, so every
  attribute it did not answer ignored the strategy; and a resolution naming a
  `MODIFIED` field was never applied.
"""

from __future__ import annotations

from metaseed.specs.merge.comparator import SpecComparator
from metaseed.specs.merge.merger import SpecMerger
from metaseed.specs.merge.models import ConflictResolution, DiffType, FieldDiff
from metaseed.specs.merge.strategies import get_strategy
from metaseed.specs.schema import FieldSpec

ORDER = ["a/1", "b/1", "c/1"]


def _analyze(specs: dict[str, FieldSpec | None]) -> tuple[DiffType, list[str]]:
    diff_type, changed, _ = SpecComparator()._analyze_field_diff(specs, ORDER)
    return diff_type, changed


def _merge(
    diff: FieldDiff, strategy: str, manual: list[ConflictResolution] | None = None
) -> FieldSpec:
    resolution_map = {
        (m.entity_name.lower(), m.field_name.lower(), m.attribute.lower()): m
        for m in manual or []
    }
    merged, _, _, unresolved = SpecMerger()._merge_entity_fields(
        "Study", [diff], ORDER, get_strategy(strategy), resolution_map, {}
    )
    assert not unresolved
    (field,) = merged
    return field


def test_a_type_conflict_is_reported_when_one_profile_lacks_the_field() -> None:
    diff_type, changed = _analyze(
        {
            "a/1": FieldSpec(name="size", type="string"),
            "b/1": FieldSpec(name="size", type="integer"),
            "c/1": None,
        }
    )
    assert diff_type == DiffType.CONFLICT
    assert "type" in changed


def test_a_type_conflict_among_profiles_adding_the_field_is_reported() -> None:
    diff_type, changed = _analyze(
        {
            "a/1": None,
            "b/1": FieldSpec(name="size", type="string"),
            "c/1": FieldSpec(name="size", type="integer"),
        }
    )
    assert diff_type == DiffType.CONFLICT
    assert "type" in changed


def test_an_agreeing_added_field_stays_added() -> None:
    diff_type, _ = _analyze(
        {
            "a/1": None,
            "b/1": FieldSpec(name="size", type="string"),
            "c/1": FieldSpec(name="size", type="string"),
        }
    )
    assert diff_type == DiffType.ADDED


def test_an_added_field_is_chosen_by_the_strategy() -> None:
    diff = FieldDiff(
        field_name="size",
        diff_type=DiffType.ADDED,
        profiles={
            "a/1": None,
            "b/1": FieldSpec(name="size", type="string", description="from b"),
            "c/1": FieldSpec(name="size", type="string", description="from c"),
        },
    )
    assert _merge(diff, "last_wins").description == "from c"


def test_a_removed_field_is_chosen_by_the_strategy() -> None:
    diff = FieldDiff(
        field_name="size",
        diff_type=DiffType.REMOVED,
        profiles={
            "a/1": FieldSpec(name="size", type="string", required=False),
            "b/1": FieldSpec(name="size", type="string", required=True),
            "c/1": None,
        },
    )
    assert _merge(diff, "most_restrictive").required is True


def test_a_manual_resolution_leaves_unanswered_attributes_to_the_strategy() -> None:
    diff = FieldDiff(
        field_name="size",
        diff_type=DiffType.CONFLICT,
        profiles={
            "a/1": FieldSpec(name="size", type="string", required=False),
            "b/1": FieldSpec(name="size", type="integer", required=True),
            "c/1": FieldSpec(name="size", type="integer", required=True),
        },
    )
    answer = ConflictResolution(
        entity_name="Study", field_name="size", attribute="type", resolved_value="float"
    )
    merged = _merge(diff, "most_restrictive", [answer])
    assert merged.type == "float"
    assert merged.required is True, "the unanswered attribute ignored the strategy"


def test_a_manual_resolution_applies_to_a_modified_field() -> None:
    diff = FieldDiff(
        field_name="size",
        diff_type=DiffType.MODIFIED,
        profiles={
            "a/1": FieldSpec(name="size", type="string", description="from a"),
            "b/1": FieldSpec(name="size", type="string", description="from b"),
            "c/1": None,
        },
    )
    answer = ConflictResolution(
        entity_name="Study",
        field_name="size",
        attribute="description",
        resolved_value="chosen",
    )
    assert _merge(diff, "first_wins", [answer]).description == "chosen"
