"""Merging profiles that mark different identifier or label fields succeeds.

Each profile may mark one field `is_identifier` and one `is_label`. When two
profiles marked different fields of the same entity, the merged entity carried
both markers and failed its own validation, so merging isa with
seek-ready-template raised instead of returning a profile.
"""

from __future__ import annotations

from metaseed.specs.merge import merge
from metaseed.specs.merge.merger import SpecMerger
from metaseed.specs.merge.models import MergeWarning
from metaseed.specs.schema import FieldSpec


def test_merging_profiles_that_label_different_fields_succeeds() -> None:
    result = merge([("isa", "1.0"), ("seek-ready-template", "3.0")])

    for name, entity in result.merged_profile.entities.items():
        for marker in ("is_identifier", "is_label"):
            marked = [f.name for f in entity.fields if getattr(f, marker)]
            assert len(marked) <= 1, f"{name} marks {marked} as {marker}"
    assert any("is_label removed" in w.message for w in result.warnings), (
        "the dropped marker was not reported"
    )


def test_the_first_marked_identifier_keeps_the_marker() -> None:
    warnings: list[MergeWarning] = []
    fields = SpecMerger()._keep_one_marked_field(
        "Study",
        [
            FieldSpec(name="identifier", type="string", is_identifier=True),
            FieldSpec(name="title", type="string", is_identifier=True, is_label=True),
        ],
        warnings,
    )

    assert [f.is_identifier for f in fields] == [True, None]
    assert fields[1].is_label is True, "an unrelated marker was removed"
    assert [w.field_name for w in warnings] == ["title"]
