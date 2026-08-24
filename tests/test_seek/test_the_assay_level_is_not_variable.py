"""`seek_level_for` names a level by the chain level alone.

Which of SEEK's two assay levels an entity is at follows from its title tag
(`entity_level`), never from the plans: a ``material`` level is
``assay - material``, the (data-file) ``assay`` level ``assay - data file``.
Before tagged profiles existed the assay level was pinned to ``data file`` and
this test pinned that; it now pins the mapping the tags select from.
"""

from __future__ import annotations

from metaseed.seek.isa_types import sample_type_attribute_plans
from metaseed.seek.templates import seek_level_for


def test_the_assay_level_is_a_data_file_level_whatever_the_plans_say() -> None:
    plans = sample_type_attribute_plans(None, level="assay", linked=False)
    assert seek_level_for("assay", plans) == "assay - data file"


def test_the_material_level_is_seeks_assay_material_level() -> None:
    assert seek_level_for("material", []) == "assay - material"


def test_the_study_levels_keep_their_own_names() -> None:
    assert seek_level_for("source", []) == "study source"
    assert seek_level_for("sample_collection", []) == "study sample"
