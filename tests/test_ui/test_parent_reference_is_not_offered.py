"""The auto-filled parent reference must not be rendered as an input (260816).

`get_field_data(exclude_parent_ref=...)` decided which field references the
parent with a string heuristic — `f"{parent.lower()}_id"` and two variants —
rather than the map the profile declares and `EntityStore._fill_parent_reference`
already uses. It matched only single-word parents with an `_id` suffix, so:

- `ObservationUnit` produced `observationunit_id`, but MIAPPE declares
  `observation_unit_id`;
- ENA names every reference `_ref` (`Experiment.study_ref`), which the suffix
  list did not cover at all.

In both cases the child-create form offered the parent reference as an editable
field the user must not fill. Filling it made `_fill_parent_reference` skip
(the value is already truthy) and the entity linked to whatever was typed.

`helper.reference_fields` maps `field -> (target entity, target field)` from the
spec's `reference:` declaration, so there is one place that knows this.
"""

from __future__ import annotations

from metaseed.facade import ProfileFacade
from metaseed.forms import get_field_data


def _names(profile: str, version: str, entity: str, parent: str) -> list[str]:
    helper = getattr(ProfileFacade(profile, version), entity)
    return [f["name"] for f in get_field_data(helper, exclude_parent_ref=parent)]


def test_a_multi_word_parent_reference_is_excluded() -> None:
    """MIAPPE: `observation_unit_id`, not `observationunit_id`."""
    assert "observation_unit_id" not in _names(
        "miappe", "1.2", "Sample", "ObservationUnit"
    )


def test_a_ref_suffixed_reference_is_excluded() -> None:
    """ENA names references `_ref`, which the suffix list never covered."""
    assert "study_ref" not in _names("ena", "1.0", "Experiment", "Study")


def test_a_single_word_parent_still_works() -> None:
    """The case the heuristic did handle must keep working."""
    assert "investigation_id" not in _names("miappe", "1.2", "Study", "Investigation")


def test_a_reference_to_a_different_entity_is_still_offered() -> None:
    """Only the parent's own reference is hidden; others are the user's to fill."""
    names = _names("ena", "1.0", "Experiment", "Study")

    assert "sample_ref" in names, names


def test_a_generated_back_reference_is_named_the_way_profiles_name_them() -> None:
    """The spec builder authors the field, so it decides the convention.

    It named the field `f"{entity.lower()}_id"`, which for a multi-word entity
    is not the snake_case every shipped profile uses — a generated profile got
    `observationunit_id` where MIAPPE has `observation_unit_id`. The reference
    is declared either way, so nothing broke; it simply produced profiles that
    do not read like the ones they sit beside.
    """
    from metaseed.specs.builder import SpecBuilder
    from metaseed.specs.schema import ProfileSpec

    builder = SpecBuilder(ProfileSpec(name="naming_probe", version="1.0"))
    builder.add_entity("ObservationUnit")
    builder.add_entity("Sample")
    builder.add_field("ObservationUnit", "samples", "list", items="Sample")

    names = [f.name for f in builder.spec.entities["Sample"].fields]

    assert "observation_unit_id" in names, names
