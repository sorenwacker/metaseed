"""Tests that verify documented behavior in docs/guides/spec-merge.md.

These tests are the source of truth validation - they verify that the
implementation matches what is documented. If a test fails, either the
docs or implementation needs to be updated to match.
"""

import pytest

from metaseed.specs.merge import (
    ComparisonResult,
    ComparisonStatistics,
    ConflictResolution,
    CSVReportGenerator,
    DiffType,
    DiffVisualizer,
    EntityDiff,
    FieldDiff,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    MergeResult,
    MergeWarning,
    compare,
    get_strategy,
    list_strategies,
    merge,
)


class TestDocumentedCompareAPI:
    """Tests for documented compare() function behavior.

    Docs section: Python API > Comparing Profiles
    """

    def test_compare_accepts_list_of_tuples(self) -> None:
        """Documented: compare([("isa", "1.0"), ("jerm", "1.0")])."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert isinstance(result, ComparisonResult)

    def test_result_has_statistics_total_entities(self) -> None:
        """Documented: result.statistics.total_entities."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result.statistics, "total_entities")
        assert isinstance(result.statistics.total_entities, int)

    def test_result_has_statistics_common_entities(self) -> None:
        """Documented: result.statistics.common_entities."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result.statistics, "common_entities")
        assert isinstance(result.statistics.common_entities, int)

    def test_result_has_statistics_conflicting_fields(self) -> None:
        """Documented: result.statistics.conflicting_fields."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result.statistics, "conflicting_fields")
        assert isinstance(result.statistics.conflicting_fields, int)

    def test_result_has_entity_diffs(self) -> None:
        """Documented: result.entity_diffs is iterable."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result, "entity_diffs")
        for entity_diff in result.entity_diffs:
            assert isinstance(entity_diff, EntityDiff)

    def test_entity_diff_has_name_and_diff_type(self) -> None:
        """Documented: entity_diff.entity_name, entity_diff.diff_type.value."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        for entity_diff in result.entity_diffs:
            assert hasattr(entity_diff, "entity_name")
            assert hasattr(entity_diff, "diff_type")
            assert isinstance(entity_diff.diff_type.value, str)

    def test_entity_diff_has_field_diffs(self) -> None:
        """Documented: entity_diff.field_diffs is iterable."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        for entity_diff in result.entity_diffs:
            assert hasattr(entity_diff, "field_diffs")
            for field_diff in entity_diff.field_diffs:
                assert isinstance(field_diff, FieldDiff)

    def test_field_diff_has_name_and_diff_type(self) -> None:
        """Documented: field_diff.field_name, field_diff.diff_type.value."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        for entity_diff in result.entity_diffs:
            for field_diff in entity_diff.field_diffs:
                assert hasattr(field_diff, "field_name")
                assert hasattr(field_diff, "diff_type")
                assert isinstance(field_diff.diff_type.value, str)


class TestDocumentedDiffTypes:
    """Tests for documented DiffType enum values.

    Docs section: Diff Types
    """

    def test_unchanged_diff_type_exists(self) -> None:
        """Documented: 'unchanged' - Identical in all compared profiles."""
        assert DiffType.UNCHANGED.value == "unchanged"

    def test_added_diff_type_exists(self) -> None:
        """Documented: 'added' - Present in compare profile, absent in base."""
        assert DiffType.ADDED.value == "added"

    def test_removed_diff_type_exists(self) -> None:
        """Documented: 'removed' - Present in base profile, absent in compare."""
        assert DiffType.REMOVED.value == "removed"

    def test_modified_diff_type_exists(self) -> None:
        """Documented: 'modified' - Present in both but with different attributes."""
        assert DiffType.MODIFIED.value == "modified"

    def test_conflict_diff_type_exists(self) -> None:
        """Documented: 'conflict' - Incompatible differences."""
        assert DiffType.CONFLICT.value == "conflict"


class TestDocumentedComparisonResult:
    """Tests for documented ComparisonResult attributes.

    Docs section: Data Models > ComparisonResult
    """

    def test_has_profiles_attribute(self) -> None:
        """Documented: profiles - List of profile identifiers compared."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result, "profiles")
        assert isinstance(result.profiles, list)

    def test_has_entity_diffs_attribute(self) -> None:
        """Documented: entity_diffs - List of EntityDiff objects."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result, "entity_diffs")
        assert isinstance(result.entity_diffs, list)

    def test_has_statistics_attribute(self) -> None:
        """Documented: statistics - ComparisonStatistics with counts."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result, "statistics")
        assert isinstance(result.statistics, ComparisonStatistics)

    def test_has_metadata_diffs_attribute(self) -> None:
        """Documented: metadata_diffs - Differences in profile metadata."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result, "metadata_diffs")

    def test_has_validation_rule_diffs_attribute(self) -> None:
        """Documented: validation_rule_diffs - Differences in validation rules."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        assert hasattr(result, "validation_rule_diffs")


class TestDocumentedEntityDiff:
    """Tests for documented EntityDiff attributes.

    Docs section: Data Models > EntityDiff
    """

    @pytest.fixture
    def entity_diff(self) -> EntityDiff:
        """Get an EntityDiff from a comparison."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        return result.entity_diffs[0]

    def test_has_entity_name(self, entity_diff: EntityDiff) -> None:
        """Documented: entity_name - Name of the entity."""
        assert hasattr(entity_diff, "entity_name")
        assert isinstance(entity_diff.entity_name, str)

    def test_has_diff_type(self, entity_diff: EntityDiff) -> None:
        """Documented: diff_type - DiffType enum value."""
        assert hasattr(entity_diff, "diff_type")
        assert isinstance(entity_diff.diff_type, DiffType)

    def test_has_profiles(self, entity_diff: EntityDiff) -> None:
        """Documented: profiles - Dict mapping profile ID to presence (bool)."""
        assert hasattr(entity_diff, "profiles")
        assert isinstance(entity_diff.profiles, dict)

    def test_has_field_diffs(self, entity_diff: EntityDiff) -> None:
        """Documented: field_diffs - List of FieldDiff objects."""
        assert hasattr(entity_diff, "field_diffs")
        assert isinstance(entity_diff.field_diffs, list)

    def test_has_has_conflicts(self, entity_diff: EntityDiff) -> None:
        """Documented: has_conflicts - Whether any fields have conflicts."""
        assert hasattr(entity_diff, "has_conflicts")
        assert isinstance(entity_diff.has_conflicts, bool)


class TestDocumentedFieldDiff:
    """Tests for documented FieldDiff attributes.

    Docs section: Data Models > FieldDiff
    """

    @pytest.fixture
    def field_diff(self) -> FieldDiff:
        """Get a FieldDiff from a comparison."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        for ed in result.entity_diffs:
            if ed.field_diffs:
                return ed.field_diffs[0]
        pytest.skip("No field diffs in comparison")

    def test_has_field_name(self, field_diff: FieldDiff) -> None:
        """Documented: field_name - Name of the field."""
        assert hasattr(field_diff, "field_name")
        assert isinstance(field_diff.field_name, str)

    def test_has_diff_type(self, field_diff: FieldDiff) -> None:
        """Documented: diff_type - DiffType enum value."""
        assert hasattr(field_diff, "diff_type")
        assert isinstance(field_diff.diff_type, DiffType)

    def test_has_profiles(self, field_diff: FieldDiff) -> None:
        """Documented: profiles - Dict mapping profile ID to FieldSpec or None."""
        assert hasattr(field_diff, "profiles")
        assert isinstance(field_diff.profiles, dict)

    def test_has_attributes_changed(self, field_diff: FieldDiff) -> None:
        """Documented: attributes_changed - List of attribute names that differ."""
        assert hasattr(field_diff, "attributes_changed")
        assert isinstance(field_diff.attributes_changed, list)

    def test_has_is_conflict(self, field_diff: FieldDiff) -> None:
        """Documented: is_conflict - Whether this is a conflict."""
        assert hasattr(field_diff, "is_conflict")
        assert isinstance(field_diff.is_conflict, bool)


class TestDocumentedComparisonStatistics:
    """Tests for documented ComparisonStatistics attributes.

    Docs section: Data Models > ComparisonStatistics
    """

    @pytest.fixture
    def stats(self) -> ComparisonStatistics:
        """Get statistics from a comparison."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        return result.statistics

    def test_has_total_entities(self, stats: ComparisonStatistics) -> None:
        """Documented: total_entities - Total unique entities across all profiles."""
        assert hasattr(stats, "total_entities")
        assert isinstance(stats.total_entities, int)

    def test_has_common_entities(self, stats: ComparisonStatistics) -> None:
        """Documented: common_entities - Entities present in all profiles."""
        assert hasattr(stats, "common_entities")
        assert isinstance(stats.common_entities, int)

    def test_has_unique_entities(self, stats: ComparisonStatistics) -> None:
        """Documented: unique_entities - Entities in only one profile."""
        assert hasattr(stats, "unique_entities")
        assert isinstance(stats.unique_entities, int)

    def test_has_modified_entities(self, stats: ComparisonStatistics) -> None:
        """Documented: modified_entities - Entities with differences."""
        assert hasattr(stats, "modified_entities")
        assert isinstance(stats.modified_entities, int)

    def test_has_total_fields(self, stats: ComparisonStatistics) -> None:
        """Documented: total_fields - Total unique fields."""
        assert hasattr(stats, "total_fields")
        assert isinstance(stats.total_fields, int)

    def test_has_common_fields(self, stats: ComparisonStatistics) -> None:
        """Documented: common_fields - Fields identical across profiles."""
        assert hasattr(stats, "common_fields")
        assert isinstance(stats.common_fields, int)

    def test_has_conflicting_fields(self, stats: ComparisonStatistics) -> None:
        """Documented: conflicting_fields - Fields with conflicts."""
        assert hasattr(stats, "conflicting_fields")
        assert isinstance(stats.conflicting_fields, int)


class TestDocumentedReportGenerators:
    """Tests for documented report generator behavior.

    Docs section: Python API > Generating Reports
    """

    @pytest.fixture
    def comparison(self) -> ComparisonResult:
        """Get a comparison result."""
        return compare([("isa", "1.0"), ("jerm", "1.0")])

    def test_markdown_generator_has_generate(self, comparison: ComparisonResult) -> None:
        """Documented: MarkdownReportGenerator(result).generate()."""
        generator = MarkdownReportGenerator(comparison)
        report = generator.generate()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_csv_generator_has_generate(self, comparison: ComparisonResult) -> None:
        """Documented: CSVReportGenerator(result).generate()."""
        generator = CSVReportGenerator(comparison)
        report = generator.generate()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_html_generator_has_generate(self, comparison: ComparisonResult) -> None:
        """Documented: HTMLReportGenerator(result).generate()."""
        generator = HTMLReportGenerator(comparison)
        report = generator.generate()
        assert isinstance(report, str)
        assert len(report) > 0


class TestDocumentedDiffVisualizer:
    """Tests for documented DiffVisualizer behavior.

    Docs section: Python API > Visualization Data
    """

    def test_build_diff_graph_returns_dict(self) -> None:
        """Documented: visualizer.build_diff_graph(result) returns graph data."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        visualizer = DiffVisualizer()
        graph_data = visualizer.build_diff_graph(result)
        assert isinstance(graph_data, dict)

    def test_graph_data_has_nodes(self) -> None:
        """Documented: graph_data contains 'nodes'."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        visualizer = DiffVisualizer()
        graph_data = visualizer.build_diff_graph(result)
        assert "nodes" in graph_data

    def test_graph_data_has_edges(self) -> None:
        """Documented: graph_data contains 'edges'."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        visualizer = DiffVisualizer()
        graph_data = visualizer.build_diff_graph(result)
        assert "edges" in graph_data

    def test_graph_data_has_legend(self) -> None:
        """Documented: graph_data contains 'legend'."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        visualizer = DiffVisualizer()
        graph_data = visualizer.build_diff_graph(result)
        assert "legend" in graph_data

    def test_graph_data_has_statistics(self) -> None:
        """Documented: graph_data contains 'statistics'."""
        result = compare([("isa", "1.0"), ("jerm", "1.0")])
        visualizer = DiffVisualizer()
        graph_data = visualizer.build_diff_graph(result)
        assert "statistics" in graph_data


class TestDocumentedMergeAPI:
    """Tests for documented merge() function behavior.

    Docs section: Profile Merging > Python API
    """

    def test_merge_accepts_profiles_and_strategy(self) -> None:
        """Documented: merge(profiles=[...], strategy='first_wins', ...)."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
            output_name="combined",
            output_version="1.0",
        )
        assert isinstance(result, MergeResult)

    def test_result_has_to_yaml(self) -> None:
        """Documented: result.to_yaml()."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
        )
        yaml_output = result.to_yaml()
        assert isinstance(yaml_output, str)
        assert "version:" in yaml_output

    def test_result_has_to_dict(self) -> None:
        """Documented: result.to_dict()."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
        )
        dict_output = result.to_dict()
        assert isinstance(dict_output, dict)

    def test_result_has_warnings(self) -> None:
        """Documented: result.warnings is iterable."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
        )
        assert hasattr(result, "warnings")
        for warning in result.warnings:
            assert isinstance(warning, MergeWarning)


class TestDocumentedMergeStrategies:
    """Tests for documented merge strategies.

    Docs section: Profile Merging > Merge Strategies
    """

    def test_first_wins_strategy(self) -> None:
        """Documented: 'first_wins' - Use first profile's value for conflicts."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
        )
        assert result.strategy_used == "first_wins"

    def test_last_wins_strategy(self) -> None:
        """Documented: 'last_wins' - Use last profile's value for conflicts."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="last_wins",
        )
        assert result.strategy_used == "last_wins"

    def test_most_restrictive_strategy(self) -> None:
        """Documented: 'most_restrictive' - required=True wins, tighter constraints."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="most_restrictive",
        )
        assert result.strategy_used == "most_restrictive"

    def test_least_restrictive_strategy(self) -> None:
        """Documented: 'least_restrictive' - required=False wins, looser constraints."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="least_restrictive",
        )
        assert result.strategy_used == "least_restrictive"

    def test_prefer_profile_strategy(self) -> None:
        """Documented: 'prefer_<profile>' - Always prefer specific profile."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="prefer_miappe/1.1",
        )
        assert "prefer" in result.strategy_used


class TestDocumentedMergeResult:
    """Tests for documented MergeResult attributes.

    Docs section: Profile Merging > MergeResult
    """

    @pytest.fixture
    def merge_result(self) -> MergeResult:
        """Get a merge result."""
        return merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
        )

    def test_has_merged_profile(self, merge_result: MergeResult) -> None:
        """Documented: merged_profile - The resulting ProfileSpec."""
        assert hasattr(merge_result, "merged_profile")

    def test_has_source_profiles(self, merge_result: MergeResult) -> None:
        """Documented: source_profiles - List of profile identifiers merged."""
        assert hasattr(merge_result, "source_profiles")
        assert isinstance(merge_result.source_profiles, list)

    def test_has_strategy_used(self, merge_result: MergeResult) -> None:
        """Documented: strategy_used - Name of the merge strategy applied."""
        assert hasattr(merge_result, "strategy_used")
        assert isinstance(merge_result.strategy_used, str)

    def test_has_resolutions_applied(self, merge_result: MergeResult) -> None:
        """Documented: resolutions_applied - List of conflict resolutions."""
        assert hasattr(merge_result, "resolutions_applied")
        assert isinstance(merge_result.resolutions_applied, list)

    def test_has_warnings(self, merge_result: MergeResult) -> None:
        """Documented: warnings - List of warnings generated."""
        assert hasattr(merge_result, "warnings")
        assert isinstance(merge_result.warnings, list)

    def test_has_has_unresolved_conflicts(self, merge_result: MergeResult) -> None:
        """Documented: has_unresolved_conflicts - Whether conflicts remain."""
        assert hasattr(merge_result, "has_unresolved_conflicts")
        assert isinstance(merge_result.has_unresolved_conflicts, bool)


class TestDocumentedConflictResolution:
    """Tests for documented ConflictResolution attributes.

    Docs section: Profile Merging > ConflictResolution
    """

    def test_has_entity_name(self) -> None:
        """Documented: entity_name - Entity containing the conflict."""
        resolution = ConflictResolution(
            entity_name="Study",
            field_name="title",
            attribute="required",
            resolved_value=True,
        )
        assert resolution.entity_name == "Study"

    def test_has_field_name(self) -> None:
        """Documented: field_name - Field with the conflict."""
        resolution = ConflictResolution(
            entity_name="Study",
            field_name="title",
            attribute="required",
            resolved_value=True,
        )
        assert resolution.field_name == "title"

    def test_has_attribute(self) -> None:
        """Documented: attribute - Attribute in conflict."""
        resolution = ConflictResolution(
            entity_name="Study",
            field_name="title",
            attribute="required",
            resolved_value=True,
        )
        assert resolution.attribute == "required"

    def test_has_resolved_value(self) -> None:
        """Documented: resolved_value - Value to use for resolution."""
        resolution = ConflictResolution(
            entity_name="Study",
            field_name="title",
            attribute="required",
            resolved_value=True,
        )
        assert resolution.resolved_value is True

    def test_has_source_profile(self) -> None:
        """Documented: source_profile - Profile the value was taken from."""
        resolution = ConflictResolution(
            entity_name="Study",
            field_name="title",
            attribute="required",
            resolved_value=True,
            source_profile="miappe/1.1",
        )
        assert resolution.source_profile == "miappe/1.1"


class TestDocumentedMergeWarning:
    """Tests for documented MergeWarning attributes.

    Docs section: Profile Merging > MergeWarning
    """

    def test_has_entity_name(self) -> None:
        """Documented: entity_name - Entity where warning occurred."""
        warning = MergeWarning(
            entity_name="Study",
            field_name="title",
            message="Test warning",
        )
        assert warning.entity_name == "Study"

    def test_has_field_name(self) -> None:
        """Documented: field_name - Field where warning occurred."""
        warning = MergeWarning(
            entity_name="Study",
            field_name="title",
            message="Test warning",
        )
        assert warning.field_name == "title"

    def test_has_message(self) -> None:
        """Documented: message - Warning message."""
        warning = MergeWarning(
            entity_name="Study",
            field_name="title",
            message="Test warning",
        )
        assert warning.message == "Test warning"

    def test_has_resolution_applied(self) -> None:
        """Documented: resolution_applied - Description of automatic resolution."""
        warning = MergeWarning(
            entity_name="Study",
            field_name="title",
            message="Test warning",
            resolution_applied="Used first profile value",
        )
        assert warning.resolution_applied == "Used first profile value"


class TestDocumentedStrategyFunctions:
    """Tests for documented strategy functions.

    Docs section: Strategy Functions
    """

    def test_list_strategies_returns_list(self) -> None:
        """Documented: list_strategies() returns list of strategy names."""
        strategies = list_strategies()
        assert strategies == [
            "first_wins",
            "last_wins",
            "most_restrictive",
            "least_restrictive",
            "prefer_<profile>",
        ]

    def test_get_strategy_returns_strategy(self) -> None:
        """Documented: get_strategy('most_restrictive') returns strategy instance."""
        strategy = get_strategy("most_restrictive")
        assert strategy is not None


class TestDocumentedManualResolution:
    """Tests for documented manual conflict resolution.

    Docs section: Manual Conflict Resolution
    """

    def test_manual_resolution_applied(self) -> None:
        """Documented: merge(..., manual_resolutions=[resolution])."""
        resolution = ConflictResolution(
            entity_name="Study",
            field_name="title",
            attribute="required",
            resolved_value=True,
            source_profile="miappe/1.1",
        )
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
            manual_resolutions=[resolution],
        )
        assert isinstance(result, MergeResult)

    def test_resolutions_applied_accessible(self) -> None:
        """Documented: result.resolutions_applied is iterable."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
        )
        for res in result.resolutions_applied:
            assert hasattr(res, "entity_name")
            assert hasattr(res, "field_name")
            assert hasattr(res, "resolved_value")
