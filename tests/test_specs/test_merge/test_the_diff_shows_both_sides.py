"""A changed field reaches the graph as both of its versions.

The visualizer used to read a field's type, required marker and nested target
from whichever profile answered first and stop there, so a field that changed
type arrived at the browser as one type with a `~` next to it: the canvas could
say that something changed but never what it changed from. A removed field was
the same accident in reverse -- its old version survived only because the base
profile happened to be first in the mapping.

Every profile's version of the field travels, ordered as the profiles were
selected, so the explorer can draw a diff: base prefixed `-`, compare `+`.
"""

from __future__ import annotations

from metaseed.specs.merge.models import (
    ComparisonResult,
    ComparisonStatistics,
    DiffType,
    EntityDiff,
    FieldDiff,
)
from metaseed.specs.merge.visualizer import DiffVisualizer
from metaseed.specs.schema import FieldSpec, FieldType

BASE = "p/1.0"
COMPARE = "p/2.0"


def _graph_field(field_diff: FieldDiff, profiles: list[str]) -> dict:
    """The field as the browser receives it, for a two-profile comparison."""
    entity = EntityDiff(
        entity_name="Source",
        diff_type=DiffType.MODIFIED,
        profiles=dict.fromkeys(profiles, True),
        field_diffs=[field_diff],
    )
    result = ComparisonResult(
        profiles=profiles,
        profile_specs={},
        entity_diffs=[entity],
        statistics=ComparisonStatistics(
            total_entities=1,
            common_entities=1,
            unique_entities=0,
            modified_entities=1,
            total_fields=1,
            common_fields=0,
            modified_fields=1,
            conflicting_fields=0,
        ),
    )
    graph = DiffVisualizer().build_diff_graph(result)
    node = next(n for n in graph["nodes"] if "Source" in n["label"])
    (field,) = node["data"]["fields"]
    return field


def test_a_changed_field_carries_both_profiles_versions() -> None:
    """The old type and the new one, not whichever came first."""
    field = _graph_field(
        FieldDiff(
            field_name="title",
            diff_type=DiffType.CONFLICT,
            profiles={
                BASE: FieldSpec(name="title", type=FieldType.STRING, required=False),
                COMPARE: FieldSpec(
                    name="title", type=FieldType.ONTOLOGY_TERM, required=True
                ),
            },
            attributes_changed=["type", "required"],
        ),
        [BASE, COMPARE],
    )

    assert field["sides"] == [
        {
            "profile": BASE,
            "present": True,
            "type": "string",
            "required": False,
            "items": None,
        },
        {
            "profile": COMPARE,
            "present": True,
            "type": "ontology_term",
            "required": True,
            "items": None,
        },
    ], "a changed field must arrive as both of its versions, in profile order"


def test_a_removed_field_still_shows_what_it_was() -> None:
    """A field only the base has: one side present, and it is the base's."""
    field = _graph_field(
        FieldDiff(
            field_name="type",
            diff_type=DiffType.REMOVED,
            profiles={
                BASE: FieldSpec(name="type", type=FieldType.STRING, required=True),
                COMPARE: None,
            },
        ),
        [BASE, COMPARE],
    )

    assert field["sides"][0] == {
        "profile": BASE,
        "present": True,
        "type": "string",
        "required": True,
        "items": None,
    }
    assert field["sides"][1]["present"] is False, (
        "the compare profile does not have the field; the graph must say so "
        "rather than repeat the base's version"
    )


def test_an_added_field_is_absent_from_the_base_side() -> None:
    field = _graph_field(
        FieldDiff(
            field_name="protocol",
            diff_type=DiffType.ADDED,
            profiles={
                BASE: None,
                COMPARE: FieldSpec(
                    name="protocol", type=FieldType.STRING, required=True
                ),
            },
        ),
        [BASE, COMPARE],
    )

    assert field["sides"][0]["present"] is False
    assert field["sides"][1]["present"] is True
    assert field["sides"][1]["type"] == "string"


def test_a_nested_field_carries_its_target_on_each_side() -> None:
    """A field repointed at another entity changed; both targets must show."""
    field = _graph_field(
        FieldDiff(
            field_name="observations",
            diff_type=DiffType.CONFLICT,
            profiles={
                BASE: FieldSpec(
                    name="observations", type=FieldType.LIST, items="Observation"
                ),
                COMPARE: FieldSpec(
                    name="observations", type=FieldType.LIST, items="ObservationUnit"
                ),
            },
            attributes_changed=["items"],
        ),
        [BASE, COMPARE],
    )

    assert [side["items"] for side in field["sides"]] == [
        "Observation",
        "ObservationUnit",
    ]
