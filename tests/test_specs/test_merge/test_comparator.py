"""Tests for spec comparator."""

import pytest

from metaseed.specs.merge import ComparisonResult, DiffType, SpecComparator, compare


class TestSpecComparator:
    """Tests for SpecComparator class."""

    @pytest.fixture
    def comparator(self) -> SpecComparator:
        """Create comparator instance."""
        return SpecComparator()

    def test_compare_requires_at_least_one_profile(self, comparator: SpecComparator) -> None:
        """Comparison requires at least 1 profile."""
        with pytest.raises(ValueError, match="At least 1 profile"):
            comparator.compare([])

    def test_explore_single_profile(self, comparator: SpecComparator) -> None:
        """Single profile returns explore result with all UNCHANGED status."""
        result = comparator.compare([("miappe", "1.2")])

        assert len(result.profiles) == 1
        assert "miappe/1.2" in result.profiles
        assert len(result.entity_diffs) > 0

        # All entities should be UNCHANGED in explore mode
        for ed in result.entity_diffs:
            assert ed.diff_type == DiffType.UNCHANGED
            # All fields should also be UNCHANGED
            for fd in ed.field_diffs:
                assert fd.diff_type == DiffType.UNCHANGED

        # Statistics should show all as common (no diffs)
        assert result.statistics.modified_entities == 0
        assert result.statistics.conflicting_fields == 0
        assert result.statistics.common_entities == result.statistics.total_entities
        assert result.statistics.common_fields == result.statistics.total_fields

    def test_compare_miappe_versions(self, comparator: SpecComparator) -> None:
        """Compare two versions of MIAPPE."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("miappe", "1.2"),
            ]
        )

        assert len(result.profiles) == 2
        assert "miappe/1.1" in result.profiles
        assert "miappe/1.2" in result.profiles
        assert len(result.entity_diffs) > 0

    def test_compare_miappe_and_isa(self, comparator: SpecComparator) -> None:
        """Compare MIAPPE and ISA profiles."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        assert len(result.profiles) == 2
        assert "miappe/1.1" in result.profiles
        assert "isa/1.0" in result.profiles

        # Both should have Investigation
        common = result.common_entities
        assert "Investigation" in common or "investigation" in [c.lower() for c in common]

    def test_compare_identifies_common_entities(self, comparator: SpecComparator) -> None:
        """Comparison identifies entities present in all profiles."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        assert result.statistics.common_entities > 0
        assert result.statistics.total_entities >= result.statistics.common_entities

    def test_compare_identifies_unique_entities(self, comparator: SpecComparator) -> None:
        """Comparison identifies entities unique to one profile."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        # ISA-specific entities like Assay
        isa_unique = result.entities_unique_to("isa/1.0")

        # MIAPPE-specific entities like BiologicalMaterial
        miappe_unique = result.entities_unique_to("miappe/1.1")

        # One or both should have unique entities
        assert len(isa_unique) > 0 or len(miappe_unique) > 0

    def test_compare_tracks_field_differences(self, comparator: SpecComparator) -> None:
        """Comparison tracks field differences within entities."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        # Get Investigation entity diff
        inv_diff = result.get_entity_diff("Investigation")
        assert inv_diff is not None
        assert len(inv_diff.field_diffs) > 0

    def test_compare_statistics(self, comparator: SpecComparator) -> None:
        """Comparison provides statistics."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        stats = result.statistics
        assert stats.total_entities > 0
        assert stats.total_fields > 0

    def test_compare_three_profiles(self, comparator: SpecComparator) -> None:
        """Compare three profiles."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("miappe", "1.2"),
                ("isa", "1.0"),
            ]
        )

        assert len(result.profiles) == 3
        assert len(result.entity_diffs) > 0


class TestCompareFunction:
    """Tests for compare() convenience function."""

    def test_compare_function(self) -> None:
        """Test compare() convenience function."""
        result = compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        assert result is not None
        assert len(result.profiles) == 2
        assert result.statistics.total_entities > 0


class TestEntityDiff:
    """Tests for entity difference analysis."""

    @pytest.fixture
    def comparison(self) -> ComparisonResult:
        """Create comparison result."""
        return compare([("miappe", "1.1"), ("isa", "1.0")])

    def test_entity_diff_has_profiles(self, comparison) -> None:
        """Entity diff tracks profile presence."""
        for ed in comparison.entity_diffs:
            assert len(ed.profiles) == 2

    def test_entity_diff_type(self, comparison) -> None:
        """Entity diff has appropriate type."""
        for ed in comparison.entity_diffs:
            assert ed.diff_type in list(DiffType)


class TestFieldDiff:
    """Tests for field difference analysis."""

    @pytest.fixture
    def comparison(self) -> ComparisonResult:
        """Create comparison result."""
        return compare([("miappe", "1.1"), ("isa", "1.0")])

    def test_field_diff_tracks_changes(self, comparison) -> None:
        """Field diff tracks attribute changes."""
        for ed in comparison.entity_diffs:
            for fd in ed.field_diffs:
                if fd.diff_type == DiffType.MODIFIED:
                    assert len(fd.attributes_changed) > 0 or fd.values

    def test_conflicting_fields_identified(self, comparison) -> None:
        """Conflicting fields are identified."""
        conflicts = comparison.conflicting_fields
        # May or may not have conflicts depending on profiles
        assert isinstance(conflicts, list)
