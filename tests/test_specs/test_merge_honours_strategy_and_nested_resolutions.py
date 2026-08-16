"""A merge must apply the strategy it was given, and survive resolving a
constraint (260816 review).

- Only `CONFLICT` consulted `strategy.resolve_field`. The comparator reserves
  that for structural disagreement (type, required, items, constraints), so a
  field differing on description, example or label was `MODIFIED` and always
  took the first profile — whichever strategy the caller chose.
- `_apply_manual_resolution` wrote the resolution's attribute straight into the
  dumped field. The comparator names a constraint conflict
  `constraints.<name>`, and `FieldSpec` forbids extra keys, so answering one
  took down the entire merge instead of resolving that field.
"""

from __future__ import annotations

from metaseed.specs.merge.merger import SpecMerger
from metaseed.specs.schema import Constraints, FieldSpec


def test_a_dotted_constraint_resolution_is_applied_not_rejected() -> None:
    merger = SpecMerger()
    base = FieldSpec(name="length", type="integer", constraints=Constraints(minimum=1))

    class _Diff:
        field_name = "length"
        profiles = {"a/1": base}

    class _Resolution:
        attribute = "constraints.minimum"
        resolved_value = 5

    resolved = merger._apply_manual_resolution(_Diff(), [_Resolution()], ["a/1"])

    assert resolved.constraints is not None
    assert resolved.constraints.minimum == 5
    assert resolved.name == "length", "the rest of the field was lost"
