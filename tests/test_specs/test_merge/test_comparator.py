"""Tests for spec comparator."""

import pytest

from metaseed.specs.merge import ComparisonResult, DiffType, SpecComparator, compare
from metaseed.specs.schema import (
    FieldSpec,
    FieldType,
    ProfileSpec,
    ValidationRuleSpec,
)


class TestSpecComparator:
    """Tests for SpecComparator class."""

    @pytest.fixture
    def comparator(self) -> SpecComparator:
        """Create comparator instance."""
        return SpecComparator()

    def test_compare_requires_at_least_one_profile(
        self, comparator: SpecComparator
    ) -> None:
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

    def test_differing_ontologies_detected_as_modified(
        self, comparator: SpecComparator
    ) -> None:
        """A field differing only in its ontologies list is flagged MODIFIED."""
        field_specs: dict[str, FieldSpec | None] = {
            "a": FieldSpec(
                name="organism",
                type=FieldType.ONTOLOGY_TERM,
                ontologies=["NCBITAXON"],
            ),
            "b": FieldSpec(
                name="organism",
                type=FieldType.ONTOLOGY_TERM,
                ontologies=["PO"],
            ),
        }
        diff_type, changed, _ = comparator._analyze_field_diff(field_specs, ["a", "b"])
        assert diff_type == DiffType.MODIFIED
        assert "ontologies" in changed

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
        assert "Investigation" in common or "investigation" in [
            c.lower() for c in common
        ]

    def test_compare_identifies_common_entities(
        self, comparator: SpecComparator
    ) -> None:
        """Comparison identifies entities present in all profiles."""
        result = comparator.compare(
            [
                ("miappe", "1.1"),
                ("isa", "1.0"),
            ]
        )

        assert result.statistics.common_entities > 0
        assert result.statistics.total_entities >= result.statistics.common_entities

    def test_compare_identifies_unique_entities(
        self, comparator: SpecComparator
    ) -> None:
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

    def test_constraint_diffs_use_flat_per_profile_shape(
        self, comparator: SpecComparator
    ) -> None:
        """A differing constraint is reported as a flat {profile: value} entry.

        Every other entry in FieldDiff.values is keyed by profile id; the
        constraint diff must match so report renderers do not drop its values.
        """
        from metaseed.specs.schema import Constraints

        field_a = FieldSpec(
            name="code",
            type=FieldType.STRING,
            constraints=Constraints(pattern="^[A-Z]+$"),
        )
        field_b = FieldSpec(
            name="code",
            type=FieldType.STRING,
            constraints=Constraints(pattern="^[a-z]+$"),
        )

        _, attributes_changed, values = comparator._analyze_field_diff(
            {"profile_a": field_a, "profile_b": field_b},
            ["profile_a", "profile_b"],
        )

        assert "constraints.pattern" in attributes_changed
        assert "constraints" not in values
        assert values["constraints.pattern"] == {
            "profile_a": "^[A-Z]+$",
            "profile_b": "^[a-z]+$",
        }

    def test_constraint_only_diff_is_a_conflict(
        self, comparator: SpecComparator
    ) -> None:
        """A field differing only in a constraint is a CONFLICT, so the merge
        strategy resolves it (e.g. 'tighter wins') rather than the merger
        silently taking the first spec.
        """
        from metaseed.specs.schema import Constraints

        field_a = FieldSpec(
            name="code", type=FieldType.STRING, constraints=Constraints(max_length=10)
        )
        field_b = FieldSpec(
            name="code", type=FieldType.STRING, constraints=Constraints(max_length=20)
        )

        diff_type, _, _ = comparator._analyze_field_diff(
            {"profile_a": field_a, "profile_b": field_b},
            ["profile_a", "profile_b"],
        )

        assert diff_type == DiffType.CONFLICT

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


class TestValidationRuleComparison:
    """Tests for validation-rule comparison behavior."""

    @pytest.fixture
    def comparator(self) -> SpecComparator:
        """Create comparator instance."""
        return SpecComparator()

    @staticmethod
    def _profile(rule: ValidationRuleSpec) -> ProfileSpec:
        """Build a minimal profile carrying a single validation rule."""
        return ProfileSpec(version="1.0", name="p", validation_rules=[rule])

    def test_same_name_different_content_is_reported(
        self, comparator: SpecComparator
    ) -> None:
        """Rules present in all profiles but differing in content are diffed."""
        spec_a = self._profile(
            ValidationRuleSpec(name="r", type="conditional", condition="a == 1")
        )
        spec_b = self._profile(
            ValidationRuleSpec(name="r", type="conditional", condition="a == 2")
        )

        diffs = comparator._compare_validation_rules({"a": spec_a, "b": spec_b})

        assert "r" in diffs

    def test_identical_rules_are_not_reported(self, comparator: SpecComparator) -> None:
        """Rules present in all profiles with identical content are not diffed."""
        rule = ValidationRuleSpec(name="r", type="conditional", condition="a == 1")
        spec_a = self._profile(rule.model_copy(deep=True))
        spec_b = self._profile(rule.model_copy(deep=True))

        diffs = comparator._compare_validation_rules({"a": spec_a, "b": spec_b})

        assert "r" not in diffs


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


class TestEveryFieldAttributeIsCompared:
    """A FieldSpec attribute added to the schema must be compared, not skipped.

    The comparator hardcoded 9 attributes while FieldSpec had grown a dozen
    more (is_identifier, options, reference_scope, ...), so two profiles
    differing only in one of those compared as UNCHANGED and the merger
    silently took the first spec. The sibling specs/compare.py derives its
    sets from FieldSpec.model_fields for exactly this reason.
    """

    def test_the_compared_set_is_derived_from_the_model(self) -> None:
        from metaseed.specs.merge.comparator import FIELD_ATTRIBUTES_TO_COMPARE
        from metaseed.specs.schema import FieldSpec

        uncompared = (
            set(FieldSpec.model_fields)
            - set(FIELD_ATTRIBUTES_TO_COMPARE)
            - {"name", "constraints"}  # identity key; compared separately
        )
        assert not uncompared, f"attributes the comparator ignores: {uncompared}"

    def test_a_difference_in_is_identifier_is_seen(self) -> None:
        from metaseed.specs.merge.comparator import SpecComparator
        from metaseed.specs.merge.models import DiffType
        from metaseed.specs.schema import FieldSpec, FieldType

        marked = FieldSpec(name="code", type=FieldType.STRING, is_identifier=True)
        plain = FieldSpec(name="code", type=FieldType.STRING)

        diff_type, changed, _values = SpecComparator()._analyze_field_diff(
            {"a/1.0": marked, "b/1.0": plain}, ["a/1.0", "b/1.0"]
        )

        assert "is_identifier" in changed
        assert diff_type is not DiffType.UNCHANGED
