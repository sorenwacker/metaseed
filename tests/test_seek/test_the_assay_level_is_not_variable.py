"""`seek_level_for` documents a choice that cannot happen (260816 review).

Its docstring says an assay level is "``assay - data file`` or ``assay -
material`` depending on what its title attribute is tagged, so it is read off
the plans rather than assumed". But `isa_types` marks exactly one plan
`is_title`, and for the assay level its tag comes from
`_LEVEL_TAGS["assay"] == ("data_file", ...)` — always `data_file`. The
`other_material` entry could never be reached, and the sentence described a
flexibility the code does not have.

This pins the actual contract: whatever plans are supplied, an assay level is
`assay - data file`. If a profile ever does produce a material-tagged title,
this test is where that decision gets made explicitly.
"""

from __future__ import annotations

from metaseed.seek.isa_types import sample_type_attribute_plans
from metaseed.seek.templates import seek_level_for


def test_every_planned_assay_level_is_a_data_file_level() -> None:
    plans = sample_type_attribute_plans(None, level="assay", linked=False)

    assert seek_level_for("assay", plans) == "assay - data file"


def test_the_non_assay_levels_keep_their_own_names() -> None:
    assert seek_level_for("source", []) == "study source"
    assert seek_level_for("sample_collection", []) == "study sample"
