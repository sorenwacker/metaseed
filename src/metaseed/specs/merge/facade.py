"""Public facade functions for spec comparison and merging.

These thin entry points are re-exported from :mod:`metaseed.specs.merge`.
"""

from metaseed.specs.loader import SpecLoader
from metaseed.specs.merge.comparator import SpecComparator
from metaseed.specs.merge.merger import merge as _merge_func
from metaseed.specs.merge.models import (
    ComparisonResult,
    ConflictResolution,
    MergeResult,
)


def compare(
    profiles: list[tuple[str, str]],
    loader: SpecLoader | None = None,
) -> ComparisonResult:
    """Compare N profile specifications.

    Args:
        profiles: List of (profile_name, version) tuples to compare.
            Example: [("miappe", "1.1"), ("isa", "1.0")]
        loader: Optional SpecLoader instance.

    Returns:
        ComparisonResult with detailed differences.

    Raises:
        ValueError: If no profiles are provided. A single profile returns an
            explore-mode ComparisonResult with all entities/fields marked
            UNCHANGED.

    Example:
        >>> result = compare([("miappe", "1.1"), ("isa", "1.0")])
        >>> print(result.common_entities)
        ['Investigation', 'Study', 'Person']
        >>> print(result.statistics.conflicting_fields)
        5
    """
    comparator = SpecComparator(loader)
    return comparator.compare(profiles)


def merge(
    profiles: list[tuple[str, str]],
    strategy: str = "first_wins",
    output_name: str = "merged",
    output_version: str = "1.0",
    manual_resolutions: list[ConflictResolution] | None = None,
) -> MergeResult:
    """Merge multiple profile specifications.

    Args:
        profiles: List of (profile_name, version) tuples to merge.
        strategy: Merge strategy name. One of:
            - "first_wins": Use first profile's values
            - "last_wins": Use last profile's values
            - "most_restrictive": required=True wins, tighter constraints
            - "least_restrictive": required=False wins, looser constraints
            - "prefer_<profile>": Always use specific profile's values
        output_name: Name for the merged profile.
        output_version: Version for the merged profile.
        manual_resolutions: Optional manual conflict resolutions.

    Returns:
        MergeResult with merged profile and metadata.

    Raises:
        ValueError: If fewer than 2 profiles provided.

    Example:
        >>> merged = merge(
        ...     profiles=[("miappe", "1.1"), ("isa", "1.0")],
        ...     strategy="most_restrictive",
        ...     output_name="combined",
        ... )
        >>> print(merged.to_yaml())
    """
    return _merge_func(
        profiles=profiles,
        strategy=strategy,
        output_name=output_name,
        output_version=output_version,
        manual_resolutions=manual_resolutions,
    )
