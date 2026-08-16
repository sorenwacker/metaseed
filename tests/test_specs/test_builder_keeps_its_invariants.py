"""The builder must enforce on add what it enforces on update (260816 review).

Three ways a draft could be given a shape the schema forbids, each surfacing
only when someone later loaded the saved profile:

- `add_field` appended a `FieldSpec` without re-validating the entity, while
  `update_field` rebuilds it through `model_validate` specifically to re-run
  the single-identifier invariant — and says so in a comment.
- `_auto_create_back_reference` decided the target already had a back-reference
  by looking only at `reference`, so a target carrying a plain field of the
  same NAME got a duplicate.
- `FieldForm.apply_to` populated a `FieldSpec` by attribute assignment, and
  pydantic does not validate assignment, so an unknown `isa_tag` reached the
  YAML unchallenged.
"""

from __future__ import annotations

import pytest

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.schema import ProfileSpec


def _builder() -> SpecBuilder:
    return SpecBuilder(ProfileSpec(name="probe", version="1.0"))


def test_a_second_identifier_is_reported_by_validation() -> None:
    """Not refused at add: the builder is add-then-validate by design.

    `update_field` re-validates because an update replaces what was there;
    `add_field` deliberately does not, so an agent can build a draft and be
    told what is wrong by `validate()` — which the MCP spec-builder tests pin
    as an issue rather than a warning. Enforcing at add would make that report
    unreachable for a spec built through the tools.
    """
    builder = _builder()
    builder.add_entity("Thing")
    builder.add_field("Thing", "a", "string", is_identifier=True)
    builder.add_field("Thing", "b", "string", is_identifier=True)

    issues = builder.validate()

    assert any("is_identifier" in str(issue) for issue in issues), issues


def test_a_generated_back_reference_does_not_duplicate_a_field_name() -> None:
    builder = _builder()
    builder.add_entity("Study")
    builder.add_entity("Sample")
    builder.add_field("Sample", "study_id", "string", description="legacy column")

    builder.add_field("Study", "samples", "list", items="Sample")

    names = [f.name for f in builder.spec.entities["Sample"].fields]
    assert len(names) == len(set(names)), names


def test_an_unknown_isa_tag_is_refused_by_the_form() -> None:
    from metaseed.specs.field_form import FieldForm

    form = FieldForm(name="x", field_type="string", isa_tag="not-a-real-tag")

    with pytest.raises(ValueError):
        form.to_field_spec()
