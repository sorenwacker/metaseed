"""Merge strategies for resolving conflicts between profiles.

This module provides pluggable strategies for resolving field conflicts
when merging profile specifications.
"""

from abc import ABC, abstractmethod
from typing import Self

from metaseed.specs.schema import Constraints, FieldSpec

from .models import FieldDiff


class MergeStrategy(ABC):
    """Base class for merge strategies.

    Merge strategies determine how to resolve conflicts when the same
    field has different values across profiles.
    """

    @property
    @abstractmethod
    def name(self: Self) -> str:
        """Return the strategy name."""

    @abstractmethod
    def resolve_field(
        self: Self,
        field_diff: FieldDiff,
        profile_order: list[str],
    ) -> FieldSpec:
        """Resolve a field conflict.

        Args:
            field_diff: The field difference to resolve.
            profile_order: Ordered list of profile IDs.

        Returns:
            Resolved FieldSpec.
        """


class FirstWinsStrategy(MergeStrategy):
    """Use the first profile's value for conflicts.

    When multiple profiles have different values for a field,
    the first profile in the list takes precedence.
    """

    @property
    def name(self: Self) -> str:
        return "first_wins"

    def resolve_field(
        self: Self,
        field_diff: FieldDiff,
        profile_order: list[str],
    ) -> FieldSpec:
        """Resolve by using first profile's field spec."""
        for profile_id in profile_order:
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                return spec

        # Should not reach here if field exists in at least one profile
        raise ValueError(f"No field spec found for {field_diff.field_name}")


class LastWinsStrategy(MergeStrategy):
    """Use the last profile's value for conflicts.

    When multiple profiles have different values for a field,
    the last profile in the list takes precedence.
    """

    @property
    def name(self: Self) -> str:
        return "last_wins"

    def resolve_field(
        self: Self,
        field_diff: FieldDiff,
        profile_order: list[str],
    ) -> FieldSpec:
        """Resolve by using last profile's field spec."""
        for profile_id in reversed(profile_order):
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                return spec

        raise ValueError(f"No field spec found for {field_diff.field_name}")


class MostRestrictiveStrategy(MergeStrategy):
    """Use the most restrictive values for conflicts.

    - required=True wins over required=False
    - Tighter constraints win (lower max, higher min)
    - Enum values are intersected
    """

    @property
    def name(self: Self) -> str:
        return "most_restrictive"

    def resolve_field(
        self: Self,
        field_diff: FieldDiff,
        profile_order: list[str],
    ) -> FieldSpec:
        """Resolve by combining most restrictive values."""
        # Start with first available spec as base
        base_spec: FieldSpec | None = None
        for profile_id in profile_order:
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                base_spec = spec
                break

        if base_spec is None:
            raise ValueError(f"No field spec found for {field_diff.field_name}")

        # Collect all specs
        all_specs = [spec for spec in field_diff.profiles.values() if spec is not None]

        # Copy the base spec so every FieldSpec attribute (including ontologies)
        # is preserved, overriding only the values this strategy recomputes.
        return base_spec.model_copy(
            update={
                "required": any(s.required for s in all_specs),  # True if any requires
                "constraints": self._merge_constraints_restrictive(all_specs),
            }
        )

    def _merge_constraints_restrictive(
        self: Self, specs: list[FieldSpec]
    ) -> Constraints | None:
        """Merge constraints using most restrictive values.

        Args:
            specs: List of field specs to merge constraints from.

        Returns:
            Merged Constraints or None.
        """
        all_constraints = [s.constraints for s in specs if s.constraints is not None]
        if not all_constraints:
            return None

        # Start with first constraint as base
        merged = Constraints()

        # Pattern: use first non-None (patterns can't be easily merged)
        for c in all_constraints:
            if c.pattern is not None:
                merged.pattern = c.pattern
                break

        # Min values: use highest (most restrictive)
        min_lengths = [
            c.min_length for c in all_constraints if c.min_length is not None
        ]
        if min_lengths:
            merged.min_length = max(min_lengths)

        minimums = [c.minimum for c in all_constraints if c.minimum is not None]
        if minimums:
            merged.minimum = max(minimums)

        min_items = [c.min_items for c in all_constraints if c.min_items is not None]
        if min_items:
            merged.min_items = max(min_items)

        # Max values: use lowest (most restrictive)
        max_lengths = [
            c.max_length for c in all_constraints if c.max_length is not None
        ]
        if max_lengths:
            merged.max_length = min(max_lengths)

        maximums = [c.maximum for c in all_constraints if c.maximum is not None]
        if maximums:
            merged.maximum = min(maximums)

        max_items = [c.max_items for c in all_constraints if c.max_items is not None]
        if max_items:
            merged.max_items = min(max_items)

        # Enum: intersect values. An empty intersection (disjoint enums) is the
        # most restrictive outcome - nothing is allowed - so keep it as an empty
        # list rather than falling back to None, which would drop the constraint.
        enums = [set(c.enum) for c in all_constraints if c.enum is not None]
        if enums:
            intersection = enums[0]
            for e in enums[1:]:
                intersection = intersection & e
            merged.enum = sorted(intersection)

        return merged


class LeastRestrictiveStrategy(MergeStrategy):
    """Use the least restrictive values for conflicts.

    - required=False wins over required=True
    - Looser constraints win (higher max, lower min)
    - Enum values are unioned
    """

    @property
    def name(self: Self) -> str:
        return "least_restrictive"

    def resolve_field(
        self: Self,
        field_diff: FieldDiff,
        profile_order: list[str],
    ) -> FieldSpec:
        """Resolve by combining least restrictive values."""
        base_spec: FieldSpec | None = None
        for profile_id in profile_order:
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                base_spec = spec
                break

        if base_spec is None:
            raise ValueError(f"No field spec found for {field_diff.field_name}")

        all_specs = [spec for spec in field_diff.profiles.values() if spec is not None]

        # Copy the base spec so every FieldSpec attribute (including ontologies)
        # is preserved, overriding only the values this strategy recomputes.
        return base_spec.model_copy(
            update={
                "required": all(s.required for s in all_specs),  # False if any optional
                "constraints": self._merge_constraints_permissive(all_specs),
            }
        )

    def _merge_constraints_permissive(
        self: Self, specs: list[FieldSpec]
    ) -> Constraints | None:
        """Merge constraints using least restrictive values.

        Args:
            specs: List of field specs to merge constraints from.

        Returns:
            Merged Constraints or None.
        """
        all_constraints = [s.constraints for s in specs if s.constraints is not None]
        if not all_constraints:
            return None

        merged = Constraints()

        # Pattern: use first non-None
        for c in all_constraints:
            if c.pattern is not None:
                merged.pattern = c.pattern
                break

        # Min values: use lowest (least restrictive)
        min_lengths = [
            c.min_length for c in all_constraints if c.min_length is not None
        ]
        if min_lengths:
            merged.min_length = min(min_lengths)

        minimums = [c.minimum for c in all_constraints if c.minimum is not None]
        if minimums:
            merged.minimum = min(minimums)

        min_items = [c.min_items for c in all_constraints if c.min_items is not None]
        if min_items:
            merged.min_items = min(min_items)

        # Max values: use highest (least restrictive)
        max_lengths = [
            c.max_length for c in all_constraints if c.max_length is not None
        ]
        if max_lengths:
            merged.max_length = max(max_lengths)

        maximums = [c.maximum for c in all_constraints if c.maximum is not None]
        if maximums:
            merged.maximum = max(maximums)

        max_items = [c.max_items for c in all_constraints if c.max_items is not None]
        if max_items:
            merged.max_items = max(max_items)

        # Enum: union values
        enums = [set(c.enum) for c in all_constraints if c.enum is not None]
        if enums:
            union = set()
            for e in enums:
                union = union | e
            merged.enum = sorted(union) if union else None

        return merged


class PreferProfileStrategy(MergeStrategy):
    """Always prefer values from a specific profile.

    Falls back to other profiles if the preferred profile
    doesn't have the field.
    """

    def __init__(self: Self, preferred_profile: str) -> None:
        """Initialize with preferred profile.

        Args:
            preferred_profile: Profile ID to prefer (e.g., "miappe/1.1").
        """
        self._preferred = preferred_profile

    @property
    def name(self: Self) -> str:
        return f"prefer_{self._preferred}"

    def resolve_field(
        self: Self,
        field_diff: FieldDiff,
        profile_order: list[str],
    ) -> FieldSpec:
        """Resolve by preferring specific profile."""
        # Try preferred profile first
        spec = field_diff.profiles.get(self._preferred)
        if spec is not None:
            return spec

        # Fall back to first available
        for profile_id in profile_order:
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                return spec

        raise ValueError(f"No field spec found for {field_diff.field_name}")


def get_strategy(name: str) -> MergeStrategy:
    """Get a merge strategy by name.

    Args:
        name: Strategy name. One of: first_wins, last_wins,
            most_restrictive, least_restrictive, prefer_<profile>.

    Returns:
        MergeStrategy instance.

    Raises:
        ValueError: If strategy name is unknown.
    """
    strategies: dict[str, type[MergeStrategy]] = {
        "first_wins": FirstWinsStrategy,
        "last_wins": LastWinsStrategy,
        "most_restrictive": MostRestrictiveStrategy,
        "least_restrictive": LeastRestrictiveStrategy,
    }

    if name in strategies:
        return strategies[name]()

    if name.startswith("prefer_"):
        profile_id = name[7:]  # Remove "prefer_" prefix
        return PreferProfileStrategy(profile_id)

    raise ValueError(
        f"Unknown strategy: {name}. Available: {', '.join(strategies.keys())}, prefer_<profile>"
    )


def list_strategies() -> list[str]:
    """List available merge strategy names.

    Returns:
        List of strategy names.
    """
    return [
        "first_wins",
        "last_wins",
        "most_restrictive",
        "least_restrictive",
        "prefer_<profile>",
    ]
