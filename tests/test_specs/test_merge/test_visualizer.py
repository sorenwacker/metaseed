"""Tests for diff visualizer edge coloring."""

import pytest

from metaseed.specs.merge.models import (
    ComparisonResult,
    ComparisonStatistics,
    DiffType,
    EntityDiff,
    FieldDiff,
)
from metaseed.specs.merge.visualizer import DiffVisualizer
from metaseed.specs.schema import FieldSpec, FieldType


class TestEdgeColoring:
    """Tests for base-relative edge coloring."""

    @pytest.fixture
    def visualizer(self) -> DiffVisualizer:
        """Create visualizer instance."""
        return DiffVisualizer()

    def _make_field_spec(
        self,
        name: str,
        field_type: str = "string",
        items: str | None = None,
    ) -> FieldSpec:
        """Create a FieldSpec for testing."""
        return FieldSpec(
            name=name,
            type=FieldType(field_type),
            required=False,
            description=f"Test field {name}",
            items=items,
        )

    def _make_comparison(
        self,
        profiles: list[str],
        entity_diffs: list[EntityDiff],
    ) -> ComparisonResult:
        """Create a ComparisonResult for testing."""
        return ComparisonResult(
            profiles=profiles,
            profile_specs={},
            entity_diffs=entity_diffs,
            statistics=ComparisonStatistics(
                total_entities=len(entity_diffs),
                common_entities=0,
                unique_entities=0,
                modified_entities=0,
                total_fields=0,
                common_fields=0,
                modified_fields=0,
                conflicting_fields=0,
            ),
        )

    def test_edge_in_both_profiles_is_gray(self, visualizer: DiffVisualizer) -> None:
        """Edge present in both base and compare profile should be gray."""
        # Create two entities: Parent and Child
        # Both profiles have Parent.children -> Child relationship
        base_profile = "base/1.0"
        compare_profile = "compare/1.0"

        parent_diff = EntityDiff(
            entity_name="Parent",
            diff_type=DiffType.UNCHANGED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[
                FieldDiff(
                    field_name="children",
                    diff_type=DiffType.UNCHANGED,
                    profiles={
                        base_profile: self._make_field_spec(
                            "children", "list", "Child"
                        ),
                        compare_profile: self._make_field_spec(
                            "children", "list", "Child"
                        ),
                    },
                ),
            ],
        )

        child_diff = EntityDiff(
            entity_name="Child",
            diff_type=DiffType.UNCHANGED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=[base_profile, compare_profile],
            entity_diffs=[parent_diff, child_diff],
        )

        graph = visualizer.build_diff_graph(comparison)

        # Find the edge from Parent to Child
        parent_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Parent")
        child_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Child")

        edge = next(
            (
                e
                for e in graph["edges"]
                if e["from"] == parent_node_id and e["to"] == child_node_id
            ),
            None,
        )

        assert edge is not None, "Edge from Parent to Child should exist"
        assert edge["color"]["color"] == "#666666", (
            "Edge in both profiles should be gray"
        )

    def test_edge_only_in_base_is_red(self, visualizer: DiffVisualizer) -> None:
        """Edge present only in base profile should be red (removed)."""
        base_profile = "base/1.0"
        compare_profile = "compare/1.0"

        # Parent exists in both, Child exists in both
        # But the relationship Parent.children -> Child only exists in base
        parent_diff = EntityDiff(
            entity_name="Parent",
            diff_type=DiffType.MODIFIED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[
                FieldDiff(
                    field_name="children",
                    diff_type=DiffType.REMOVED,
                    profiles={
                        base_profile: self._make_field_spec(
                            "children", "list", "Child"
                        ),
                        compare_profile: None,  # Field removed in compare
                    },
                ),
            ],
        )

        child_diff = EntityDiff(
            entity_name="Child",
            diff_type=DiffType.UNCHANGED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=[base_profile, compare_profile],
            entity_diffs=[parent_diff, child_diff],
        )

        graph = visualizer.build_diff_graph(comparison)

        parent_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Parent")
        child_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Child")

        edge = next(
            (
                e
                for e in graph["edges"]
                if e["from"] == parent_node_id and e["to"] == child_node_id
            ),
            None,
        )

        assert edge is not None, "Edge from Parent to Child should exist"
        assert edge["color"]["color"] == "#f44336", (
            "Edge only in base should be red (removed)"
        )

    def test_edge_only_in_compare_is_green(self, visualizer: DiffVisualizer) -> None:
        """Edge present only in compare profile should be green (added)."""
        base_profile = "base/1.0"
        compare_profile = "compare/1.0"

        # Parent exists in both, Child exists in both
        # But the relationship Parent.children -> Child only exists in compare
        parent_diff = EntityDiff(
            entity_name="Parent",
            diff_type=DiffType.MODIFIED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[
                FieldDiff(
                    field_name="children",
                    diff_type=DiffType.ADDED,
                    profiles={
                        base_profile: None,  # Field doesn't exist in base
                        compare_profile: self._make_field_spec(
                            "children", "list", "Child"
                        ),
                    },
                ),
            ],
        )

        child_diff = EntityDiff(
            entity_name="Child",
            diff_type=DiffType.UNCHANGED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=[base_profile, compare_profile],
            entity_diffs=[parent_diff, child_diff],
        )

        graph = visualizer.build_diff_graph(comparison)

        parent_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Parent")
        child_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Child")

        edge = next(
            (
                e
                for e in graph["edges"]
                if e["from"] == parent_node_id and e["to"] == child_node_id
            ),
            None,
        )

        assert edge is not None, "Edge from Parent to Child should exist"
        assert edge["color"]["color"] == "#4caf50", (
            "Edge only in compare should be green (added)"
        )

    def test_edge_to_added_entity_is_green(self, visualizer: DiffVisualizer) -> None:
        """Edge to an entity that only exists in compare should be green."""
        base_profile = "base/1.0"
        compare_profile = "compare/1.0"

        # Parent exists in both, but Child only exists in compare
        parent_diff = EntityDiff(
            entity_name="Parent",
            diff_type=DiffType.MODIFIED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[
                FieldDiff(
                    field_name="children",
                    diff_type=DiffType.ADDED,
                    profiles={
                        base_profile: None,
                        compare_profile: self._make_field_spec(
                            "children", "list", "Child"
                        ),
                    },
                ),
            ],
        )

        child_diff = EntityDiff(
            entity_name="Child",
            diff_type=DiffType.ADDED,
            profiles={base_profile: False, compare_profile: True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=[base_profile, compare_profile],
            entity_diffs=[parent_diff, child_diff],
        )

        graph = visualizer.build_diff_graph(comparison)

        parent_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Parent")
        child_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Child")

        edge = next(
            (
                e
                for e in graph["edges"]
                if e["from"] == parent_node_id and e["to"] == child_node_id
            ),
            None,
        )

        assert edge is not None, "Edge from Parent to Child should exist"
        assert edge["color"]["color"] == "#4caf50", (
            "Edge to added entity should be green"
        )

    def test_edge_from_removed_entity_is_red(self, visualizer: DiffVisualizer) -> None:
        """Edge from an entity that only exists in base should be red."""
        base_profile = "base/1.0"
        compare_profile = "compare/1.0"

        # Parent only exists in base, Child exists in both
        parent_diff = EntityDiff(
            entity_name="Parent",
            diff_type=DiffType.REMOVED,
            profiles={base_profile: True, compare_profile: False},
            field_diffs=[
                FieldDiff(
                    field_name="children",
                    diff_type=DiffType.REMOVED,
                    profiles={
                        base_profile: self._make_field_spec(
                            "children", "list", "Child"
                        ),
                        compare_profile: None,
                    },
                ),
            ],
        )

        child_diff = EntityDiff(
            entity_name="Child",
            diff_type=DiffType.UNCHANGED,
            profiles={base_profile: True, compare_profile: True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=[base_profile, compare_profile],
            entity_diffs=[parent_diff, child_diff],
        )

        graph = visualizer.build_diff_graph(comparison)

        parent_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Parent")
        child_node_id = next(n["id"] for n in graph["nodes"] if n["label"] == "Child")

        edge = next(
            (
                e
                for e in graph["edges"]
                if e["from"] == parent_node_id and e["to"] == child_node_id
            ),
            None,
        )

        assert edge is not None, "Edge from Parent to Child should exist"
        assert edge["color"]["color"] == "#f44336", (
            "Edge from removed entity should be red"
        )


class TestNodeColoring:
    """Tests for entity node coloring."""

    @pytest.fixture
    def visualizer(self) -> DiffVisualizer:
        """Create visualizer instance."""
        return DiffVisualizer()

    def _make_comparison(
        self,
        profiles: list[str],
        entity_diffs: list[EntityDiff],
    ) -> ComparisonResult:
        """Create a ComparisonResult for testing."""
        return ComparisonResult(
            profiles=profiles,
            profile_specs={},
            entity_diffs=entity_diffs,
            statistics=ComparisonStatistics(),
        )

    def test_unchanged_entity_is_gray(self, visualizer: DiffVisualizer) -> None:
        """Entity in both profiles should be gray."""
        entity_diff = EntityDiff(
            entity_name="TestEntity",
            diff_type=DiffType.UNCHANGED,
            profiles={"base/1.0": True, "compare/1.0": True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=["base/1.0", "compare/1.0"],
            entity_diffs=[entity_diff],
        )

        graph = visualizer.build_diff_graph(comparison)
        node = graph["nodes"][0]

        assert node["color"]["background"] == "#e0e0e0"
        assert node["color"]["border"] == "#9e9e9e"

    def test_added_entity_is_green(self, visualizer: DiffVisualizer) -> None:
        """Entity only in compare profile should be green."""
        entity_diff = EntityDiff(
            entity_name="TestEntity",
            diff_type=DiffType.ADDED,
            profiles={"base/1.0": False, "compare/1.0": True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=["base/1.0", "compare/1.0"],
            entity_diffs=[entity_diff],
        )

        graph = visualizer.build_diff_graph(comparison)
        node = graph["nodes"][0]

        assert node["color"]["background"] == "#c8e6c9"
        assert node["color"]["border"] == "#4caf50"

    def test_removed_entity_is_red(self, visualizer: DiffVisualizer) -> None:
        """Entity only in base profile should be red."""
        entity_diff = EntityDiff(
            entity_name="TestEntity",
            diff_type=DiffType.REMOVED,
            profiles={"base/1.0": True, "compare/1.0": False},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=["base/1.0", "compare/1.0"],
            entity_diffs=[entity_diff],
        )

        graph = visualizer.build_diff_graph(comparison)
        node = graph["nodes"][0]

        assert node["color"]["background"] == "#ffcdd2"
        assert node["color"]["border"] == "#f44336"

    def test_modified_entity_is_amber(self, visualizer: DiffVisualizer) -> None:
        """Entity with different fields should be amber."""
        entity_diff = EntityDiff(
            entity_name="TestEntity",
            diff_type=DiffType.MODIFIED,
            profiles={"base/1.0": True, "compare/1.0": True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=["base/1.0", "compare/1.0"],
            entity_diffs=[entity_diff],
        )

        graph = visualizer.build_diff_graph(comparison)
        node = graph["nodes"][0]

        assert node["color"]["background"] == "#fff3e0"
        assert node["color"]["border"] == "#ff9800"

    def test_conflict_entity_is_dark_red(self, visualizer: DiffVisualizer) -> None:
        """Entity with conflicts should be dark red."""
        entity_diff = EntityDiff(
            entity_name="TestEntity",
            diff_type=DiffType.CONFLICT,
            profiles={"base/1.0": True, "compare/1.0": True},
            field_diffs=[],
        )

        comparison = self._make_comparison(
            profiles=["base/1.0", "compare/1.0"],
            entity_diffs=[entity_diff],
        )

        graph = visualizer.build_diff_graph(comparison)
        node = graph["nodes"][0]

        assert node["color"]["background"] == "#ffebee"
        assert node["color"]["border"] == "#d32f2f"


def test_a_field_with_an_enum_carries_its_vocabulary_into_the_graph() -> None:
    # The explorer shows a field's controlled vocabulary from this; without the
    # terms in the graph data there was nowhere in the UI to see them.
    from metaseed.specs.merge.models import (
        ComparisonResult,
        ComparisonStatistics,
        DiffType,
        EntityDiff,
        FieldDiff,
    )
    from metaseed.specs.schema import Constraints

    spec = FieldSpec(
        name="growth_medium",
        type=FieldType.STRING,
        constraints=Constraints(enum=["soil", "hydroponic"]),
    )
    field = FieldDiff(
        field_name="growth_medium",
        diff_type=DiffType.UNCHANGED,
        profiles={"p/1.0": spec},
    )
    entity = EntityDiff(
        entity_name="Source",
        diff_type=DiffType.UNCHANGED,
        profiles={"p/1.0": True},
        field_diffs=[field],
    )
    result = ComparisonResult(
        profiles=["p/1.0"],
        profile_specs={},
        entity_diffs=[entity],
        statistics=ComparisonStatistics(
            total_entities=1,
            common_entities=1,
            unique_entities=0,
            modified_entities=0,
            total_fields=1,
            common_fields=1,
            modified_fields=0,
            conflicting_fields=0,
        ),
    )
    graph = DiffVisualizer().build_diff_graph(result)
    node = next(n for n in graph["nodes"] if "Source" in n["label"])
    (growth,) = [f for f in node["data"]["fields"] if f["name"] == "growth_medium"]
    assert growth["vocabulary"] == ["soil", "hydroponic"]


def _single_profile_result(spec_yaml: dict) -> "ComparisonResult":
    """A one-profile comparison, the explorer's 'explore only' mode.

    The comparator loads profiles by name through a loader; handing it one
    that answers with this spec keeps the test off the filesystem.
    """
    from metaseed.specs.merge.comparator import SpecComparator
    from metaseed.specs.schema import ProfileSpec

    spec = ProfileSpec.model_validate(spec_yaml)

    class _Loader:
        def load_profile(self, version=None, profile=None, **_kw):
            return spec

        def list_versions(self, *_a, **_k):
            return [spec.version]

    return SpecComparator(loader=_Loader()).compare([("p", "1.0")])


_RICH_PROFILE = {
    "spec_version": "0.1",
    "version": "1.0",
    "name": "p",
    "display_name": "P",
    "description": "A profile with details.",
    "root_entity": "Study",
    "entities": {
        "Study": {
            "description": "A study is a unit of work.",
            "ontology_term": "OBI:0000066",
            "seek": {"role": "Study", "extended_metadata": "CropXR study"},
            "fields": [
                {
                    "name": "identifier",
                    "type": "string",
                    "required": True,
                    "is_identifier": True,
                    "description": "The study's id.",
                    "constraints": {"pattern": "^S-[0-9]+$", "max_length": 12},
                    "isa_tag": "sample",
                    "seek_attribute_type": "String",
                },
                {"name": "title", "type": "string", "unit": None},
            ],
        }
    },
    "validation_rules": [
        {
            "name": "study_has_title",
            "description": "A study needs a title.",
            "type": "required",
            "applies_to": ["Study"],
            "field": "title",
            "message": "Give the study a title.",
        },
        {
            "name": "everything_has_an_id",
            "description": "Every entity carries an identifier.",
            "type": "required",
            "applies_to": "all",
            "field": "identifier",
        },
    ],
}


def test_a_field_carries_every_attribute_it_has_set_into_the_graph() -> None:
    # The explorer showed a field as name and type only; description,
    # constraints, markers and SEEK columns were invisible from the UI.
    graph = DiffVisualizer().build_diff_graph(_single_profile_result(_RICH_PROFILE))
    node = next(n for n in graph["nodes"] if n["data"].get("name") == "Study")
    ident = next(f for f in node["data"]["fields"] if f["name"] == "identifier")
    details = ident["details"]
    assert details["description"] == "The study's id."
    assert details["is_identifier"] is True
    assert details["constraints"] == {"pattern": "^S-[0-9]+$", "max_length": 12}
    assert details["isa_tag"] == "sample"
    assert details["seek_attribute_type"] == "String"
    title = next(f for f in node["data"]["fields"] if f["name"] == "title")
    assert title["details"] == {}, "an attribute that is not set is not shown as set"


def test_an_entity_carries_its_description_and_term() -> None:
    graph = DiffVisualizer().build_diff_graph(_single_profile_result(_RICH_PROFILE))
    node = next(n for n in graph["nodes"] if n["data"].get("name") == "Study")
    assert node["data"]["description"] == "A study is a unit of work."
    assert node["data"]["ontology_term"] == "OBI:0000066"


def test_validation_rules_reach_the_graph_and_each_entity_gets_its_own() -> None:
    graph = DiffVisualizer().build_diff_graph(_single_profile_result(_RICH_PROFILE))
    assert [r["name"] for r in graph["rules"]["p/1.0"]] == [
        "study_has_title",
        "everything_has_an_id",
    ]
    node = next(n for n in graph["nodes"] if n["data"].get("name") == "Study")
    # Both apply: one names the entity, the other says "all".
    assert [r["name"] for r in node["data"]["rules"]] == [
        "study_has_title",
        "everything_has_an_id",
    ]
    named = node["data"]["rules"][0]
    assert named["message"] == "Give the study a title."
    assert named["field"] == "title"
    assert "pattern" not in named, "unset parameters are not listed"


def test_the_entity_carries_its_seek_mapping_and_the_graph_the_profile_metadata() -> (
    None
):
    # The builder's profile form and the entity's SEEK block had no place in
    # the explorer; a person had to open the builder to see either.
    graph = DiffVisualizer().build_diff_graph(_single_profile_result(_RICH_PROFILE))
    node = next(n for n in graph["nodes"] if n["data"].get("name") == "Study")
    assert node["data"]["seek"] == {
        "role": "Study",
        "extended_metadata": "CropXR study",
    }
    meta = graph["profiles_meta"]["p/1.0"]
    assert meta["display_name"] == "P"
    assert meta["description"] == "A profile with details."
    assert meta["root_entity"] == "Study"
