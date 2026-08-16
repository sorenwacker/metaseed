"""Set in one profile and absent in another IS a difference (260816 review).

`_values_differ` and `_compare_metadata` both filtered `None` out before
counting distinct values, so `{'a': None, 'b': 'MIAPPE:DM-1'}` collapsed to one
value and reported no difference. Comparing two profiles where one carries an
ontology term, description or display name and the other does not therefore
said they agree — the single question a comparison exists to answer.
"""

from __future__ import annotations

from metaseed.specs.merge.comparator import SpecComparator


def _differ(values: dict[str, object]) -> bool:
    return SpecComparator()._values_differ(values)


def test_present_in_one_profile_and_absent_in_the_other_differs() -> None:
    assert _differ({"a/1": None, "b/1": "MIAPPE:DM-1"})


def test_absent_everywhere_is_not_a_difference() -> None:
    assert not _differ({"a/1": None, "b/1": None})


def test_the_same_value_everywhere_is_not_a_difference() -> None:
    assert not _differ({"a/1": "MIAPPE:DM-1", "b/1": "MIAPPE:DM-1"})


def test_two_different_values_still_differ() -> None:
    assert _differ({"a/1": "MIAPPE:DM-1", "b/1": "MIAPPE:DM-2"})
