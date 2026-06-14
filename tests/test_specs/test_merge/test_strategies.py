"""Tests for merge strategies."""

import pytest

from metaseed.specs.merge import (
    FirstWinsStrategy,
    LastWinsStrategy,
    LeastRestrictiveStrategy,
    MostRestrictiveStrategy,
    PreferProfileStrategy,
    get_strategy,
    list_strategies,
)
from metaseed.specs.merge.models import DiffType, FieldDiff
from metaseed.specs.schema import Constraints, FieldSpec, FieldType


class TestGetStrategy:
    """Tests for get_strategy function."""

    def test_get_first_wins(self) -> None:
        """Get first_wins strategy."""
        strategy = get_strategy("first_wins")
        assert isinstance(strategy, FirstWinsStrategy)
        assert strategy.name == "first_wins"

    def test_get_last_wins(self) -> None:
        """Get last_wins strategy."""
        strategy = get_strategy("last_wins")
        assert isinstance(strategy, LastWinsStrategy)
        assert strategy.name == "last_wins"

    def test_get_most_restrictive(self) -> None:
        """Get most_restrictive strategy."""
        strategy = get_strategy("most_restrictive")
        assert isinstance(strategy, MostRestrictiveStrategy)
        assert strategy.name == "most_restrictive"

    def test_get_least_restrictive(self) -> None:
        """Get least_restrictive strategy."""
        strategy = get_strategy("least_restrictive")
        assert isinstance(strategy, LeastRestrictiveStrategy)
        assert strategy.name == "least_restrictive"

    def test_get_prefer_profile(self) -> None:
        """Get prefer_<profile> strategy."""
        strategy = get_strategy("prefer_miappe/1.1")
        assert isinstance(strategy, PreferProfileStrategy)
        assert strategy.name == "prefer_miappe/1.1"

    def test_unknown_strategy_raises(self) -> None:
        """Unknown strategy raises ValueError."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("invalid_strategy")


class TestListStrategies:
    """Tests for list_strategies function."""

    def test_list_strategies(self) -> None:
        """List available strategies."""
        strategies = list_strategies()
        assert "first_wins" in strategies
        assert "last_wins" in strategies
        assert "most_restrictive" in strategies
        assert "least_restrictive" in strategies
        assert "prefer_<profile>" in strategies


class TestFirstWinsStrategy:
    """Tests for FirstWinsStrategy."""

    @pytest.fixture
    def strategy(self) -> FirstWinsStrategy:
        """Create strategy instance."""
        return FirstWinsStrategy()

    @pytest.fixture
    def field_diff(self) -> FieldDiff:
        """Create test field diff."""
        return FieldDiff(
            field_name="test_field",
            diff_type=DiffType.CONFLICT,
            profiles={
                "profile_a": FieldSpec(
                    name="test_field",
                    type=FieldType.STRING,
                    required=True,
                    description="From A",
                ),
                "profile_b": FieldSpec(
                    name="test_field",
                    type=FieldType.STRING,
                    required=False,
                    description="From B",
                ),
            },
        )

    def test_first_wins_uses_first_profile(
        self, strategy: FirstWinsStrategy, field_diff: FieldDiff
    ) -> None:
        """First wins strategy uses first profile's value."""
        resolved = strategy.resolve_field(field_diff, ["profile_a", "profile_b"])
        assert resolved.required is True
        assert resolved.description == "From A"

    def test_first_wins_skips_missing(self, strategy: FirstWinsStrategy) -> None:
        """First wins skips profiles where field is missing."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.ADDED,
            profiles={
                "profile_a": None,
                "profile_b": FieldSpec(
                    name="test", type=FieldType.STRING, description="B"
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["profile_a", "profile_b"])
        assert resolved.description == "B"


class TestLastWinsStrategy:
    """Tests for LastWinsStrategy."""

    @pytest.fixture
    def strategy(self) -> LastWinsStrategy:
        """Create strategy instance."""
        return LastWinsStrategy()

    def test_last_wins_uses_last_profile(self, strategy: LastWinsStrategy) -> None:
        """Last wins strategy uses last profile's value."""
        diff = FieldDiff(
            field_name="test_field",
            diff_type=DiffType.CONFLICT,
            profiles={
                "profile_a": FieldSpec(
                    name="test_field",
                    type=FieldType.STRING,
                    required=True,
                    description="From A",
                ),
                "profile_b": FieldSpec(
                    name="test_field",
                    type=FieldType.STRING,
                    required=False,
                    description="From B",
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["profile_a", "profile_b"])
        assert resolved.required is False
        assert resolved.description == "From B"


class TestMostRestrictiveStrategy:
    """Tests for MostRestrictiveStrategy."""

    @pytest.fixture
    def strategy(self) -> MostRestrictiveStrategy:
        """Create strategy instance."""
        return MostRestrictiveStrategy()

    def test_required_true_wins(self, strategy: MostRestrictiveStrategy) -> None:
        """required=True wins over required=False."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(name="test", type=FieldType.STRING, required=False),
                "b": FieldSpec(name="test", type=FieldType.STRING, required=True),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.required is True

    def test_tighter_max_wins(self, strategy: MostRestrictiveStrategy) -> None:
        """Lower max_length wins."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(max_length=100),
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(max_length=50),
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.constraints is not None
        assert resolved.constraints.max_length == 50

    def test_higher_min_wins(self, strategy: MostRestrictiveStrategy) -> None:
        """Higher min_length wins."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(min_length=5),
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(min_length=10),
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.constraints is not None
        assert resolved.constraints.min_length == 10

    def test_enum_intersection(self, strategy: MostRestrictiveStrategy) -> None:
        """Enum values are intersected."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["x", "y", "z"]),
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["y", "z", "w"]),
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.constraints is not None
        assert set(resolved.constraints.enum) == {"y", "z"}

    def test_disjoint_enum_yields_empty_not_none(
        self, strategy: MostRestrictiveStrategy
    ) -> None:
        """Disjoint enums intersect to an empty list, not None (no constraint)."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["x"]),
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["y"]),
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.constraints is not None
        assert resolved.constraints.enum == []

    def test_ontologies_preserved(self, strategy: MostRestrictiveStrategy) -> None:
        """The base spec's ontologies list survives the merge."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.ONTOLOGY_TERM,
                    required=False,
                    ontologies=["AGRO", "PO"],
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.ONTOLOGY_TERM,
                    required=True,
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.ontologies == ["AGRO", "PO"]
        assert resolved.required is True


class TestLeastRestrictiveStrategy:
    """Tests for LeastRestrictiveStrategy."""

    @pytest.fixture
    def strategy(self) -> LeastRestrictiveStrategy:
        """Create strategy instance."""
        return LeastRestrictiveStrategy()

    def test_required_false_wins(self, strategy: LeastRestrictiveStrategy) -> None:
        """required=False wins over required=True."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(name="test", type=FieldType.STRING, required=True),
                "b": FieldSpec(name="test", type=FieldType.STRING, required=False),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.required is False

    def test_higher_max_wins(self, strategy: LeastRestrictiveStrategy) -> None:
        """Higher max_length wins."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(max_length=100),
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(max_length=50),
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.constraints is not None
        assert resolved.constraints.max_length == 100

    def test_enum_union(self, strategy: LeastRestrictiveStrategy) -> None:
        """Enum values are unioned."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["x", "y"]),
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["y", "z"]),
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.constraints is not None
        assert set(resolved.constraints.enum) == {"x", "y", "z"}

    def test_ontologies_preserved(self, strategy: LeastRestrictiveStrategy) -> None:
        """The base spec's ontologies list survives the merge."""
        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "a": FieldSpec(
                    name="test",
                    type=FieldType.ONTOLOGY_TERM,
                    required=True,
                    ontologies=["AGRO", "PO"],
                ),
                "b": FieldSpec(
                    name="test",
                    type=FieldType.ONTOLOGY_TERM,
                    required=False,
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["a", "b"])
        assert resolved.ontologies == ["AGRO", "PO"]
        assert resolved.required is False


class TestPreferProfileStrategy:
    """Tests for PreferProfileStrategy."""

    def test_prefers_specified_profile(self) -> None:
        """Strategy prefers specified profile."""
        strategy = PreferProfileStrategy("profile_b")

        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.CONFLICT,
            profiles={
                "profile_a": FieldSpec(
                    name="test", type=FieldType.STRING, description="A"
                ),
                "profile_b": FieldSpec(
                    name="test", type=FieldType.STRING, description="B"
                ),
            },
        )
        resolved = strategy.resolve_field(diff, ["profile_a", "profile_b"])
        assert resolved.description == "B"

    def test_falls_back_if_missing(self) -> None:
        """Falls back to other profile if preferred missing."""
        strategy = PreferProfileStrategy("profile_b")

        diff = FieldDiff(
            field_name="test",
            diff_type=DiffType.ADDED,
            profiles={
                "profile_a": FieldSpec(
                    name="test", type=FieldType.STRING, description="A"
                ),
                "profile_b": None,
            },
        )
        resolved = strategy.resolve_field(diff, ["profile_a", "profile_b"])
        assert resolved.description == "A"
