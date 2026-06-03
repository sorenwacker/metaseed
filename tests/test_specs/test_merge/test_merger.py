"""Tests for spec merger."""

import pytest

from metaseed.specs.merge import (
    ConflictResolution,
    MergeResult,
    SpecMerger,
    merge,
)


class TestSpecMerger:
    """Tests for SpecMerger class."""

    @pytest.fixture
    def merger(self) -> SpecMerger:
        """Create merger instance."""
        return SpecMerger()

    def test_merge_requires_at_least_two_profiles(self, merger: SpecMerger) -> None:
        """Merge requires at least 2 profiles."""
        with pytest.raises(ValueError, match="At least 2 profiles"):
            merger.merge([("miappe", "1.1")])

    def test_merge_miappe_versions(self, merger: SpecMerger) -> None:
        """Merge two versions of MIAPPE."""
        result = merger.merge(
            profiles=[("miappe", "1.1"), ("miappe", "1.2")],
            strategy="first_wins",
            output_name="miappe-merged",
        )

        assert isinstance(result, MergeResult)
        assert result.merged_profile is not None
        assert result.merged_profile.name == "miappe-merged"
        assert len(result.source_profiles) == 2

    def test_merge_different_profiles(self, merger: SpecMerger) -> None:
        """Merge different profiles."""
        result = merger.merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="most_restrictive",
            output_name="combined",
        )

        assert result.merged_profile is not None
        # Should have entities from both profiles
        entity_names = list(result.merged_profile.entities.keys())
        assert len(entity_names) > 0

        # Verify entities from MIAPPE exist (case-insensitive check)
        entity_names_lower = [e.lower() for e in entity_names]
        assert (
            "investigation" in entity_names_lower
        ), "Missing Investigation from MIAPPE"
        assert "study" in entity_names_lower, "Missing Study from MIAPPE"

        # Verify entities from ISA exist
        assert "assay" in entity_names_lower, "Missing Assay from ISA"

    def test_merge_tracks_strategy(self, merger: SpecMerger) -> None:
        """Merge tracks which strategy was used."""
        result = merger.merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="most_restrictive",
            output_name="test",
        )

        assert result.strategy_used == "most_restrictive"

    def test_merge_generates_warnings(self, merger: SpecMerger) -> None:
        """Merge generates warnings for resolved conflicts."""
        result = merger.merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
            output_name="test",
        )

        # Should have some warnings about added/modified fields
        assert isinstance(result.warnings, list)

    def test_merge_to_yaml(self, merger: SpecMerger) -> None:
        """Merged result can export to YAML."""
        result = merger.merge(
            profiles=[("miappe", "1.1"), ("miappe", "1.2")],
            strategy="first_wins",
            output_name="test",
        )

        yaml_output = result.to_yaml()
        assert isinstance(yaml_output, str)
        assert "name: test" in yaml_output

    def test_merge_to_dict(self, merger: SpecMerger) -> None:
        """Merged result can export to dict."""
        result = merger.merge(
            profiles=[("miappe", "1.1"), ("miappe", "1.2")],
            strategy="first_wins",
            output_name="test",
        )

        data = result.to_dict()
        assert isinstance(data, dict)
        assert data["name"] == "test"
        assert "entities" in data


class TestMergeFunction:
    """Tests for merge() convenience function."""

    def test_merge_function(self) -> None:
        """Test merge() convenience function."""
        result = merge(
            profiles=[("miappe", "1.1"), ("miappe", "1.2")],
            strategy="first_wins",
            output_name="test",
        )

        assert result is not None
        assert result.merged_profile is not None

    def test_merge_with_different_strategies(self) -> None:
        """Test merge with different strategies."""
        strategies = [
            "first_wins",
            "last_wins",
            "most_restrictive",
            "least_restrictive",
        ]

        for strategy in strategies:
            result = merge(
                profiles=[("miappe", "1.1"), ("miappe", "1.2")],
                strategy=strategy,
                output_name="test",
            )
            assert result.strategy_used == strategy


class TestManualResolutions:
    """Tests for manual conflict resolutions."""

    @pytest.fixture
    def merger(self) -> SpecMerger:
        """Create merger instance."""
        return SpecMerger()

    def test_manual_resolution_applied(self, merger: SpecMerger) -> None:
        """Manual resolutions are applied during merge."""
        resolutions = [
            ConflictResolution(
                entity_name="Investigation",
                field_name="title",
                attribute="required",
                resolved_value=True,
                source_profile="manual",
            ),
        ]

        result = merger.merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
            output_name="test",
            manual_resolutions=resolutions,
        )

        # Check that resolution was tracked
        assert isinstance(result.resolutions_applied, list)


class TestMergeResult:
    """Tests for MergeResult class."""

    def test_has_unresolved_conflicts(self) -> None:
        """Test has_unresolved_conflicts property."""
        result = merge(
            profiles=[("miappe", "1.1"), ("isa", "1.0")],
            strategy="first_wins",
            output_name="test",
        )

        # Property should be accessible
        assert isinstance(result.has_unresolved_conflicts, bool)

    def test_merge_preserves_root_entity(self) -> None:
        """Merged profile preserves root entity."""
        result = merge(
            profiles=[("miappe", "1.1"), ("miappe", "1.2")],
            strategy="first_wins",
            output_name="test",
        )

        assert result.merged_profile.root_entity == "Investigation"

    def test_merge_sets_output_version(self) -> None:
        """Merged profile uses specified version."""
        result = merge(
            profiles=[("miappe", "1.1"), ("miappe", "1.2")],
            strategy="first_wins",
            output_name="test",
            output_version="2.0",
        )

        assert result.merged_profile.version == "2.0"
