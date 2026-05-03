"""Spec comparison and merge library.

This module provides tools for comparing N profile specifications and
merging them with configurable conflict resolution strategies.

Example usage:

    from metaseed.specs.merge import compare, merge

    # Compare profiles
    result = compare([("miappe", "1.1"), ("isa", "1.0")])
    print(result.common_entities)
    print(result.conflicting_fields)

    # Merge profiles
    merged = merge(
        profiles=[("miappe", "1.1"), ("isa", "1.0")],
        strategy="most_restrictive",
        output_name="combined",
    )
    print(merged.to_yaml())

    # Generate reports
    from metaseed.specs.merge import MarkdownReportGenerator
    report = MarkdownReportGenerator(result).generate()

    # Get ERD visualization data
    from metaseed.specs.merge import DiffVisualizer
    graph_data = DiffVisualizer().build_diff_graph(result)
"""

from metaseed.specs.loader import SpecLoader

from .comparator import SpecComparator
from .merger import SpecMerger
from .merger import merge as _merge_func
from .models import (
    ComparisonResult,
    ComparisonStatistics,
    ConflictResolution,
    DiffType,
    EntityDiff,
    FieldDiff,
    MergeResult,
    MergeWarning,
)
from .reports import (
    CSVReportGenerator,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    ReportGenerator,
)
from .strategies import (
    FirstWinsStrategy,
    LastWinsStrategy,
    LeastRestrictiveStrategy,
    MergeStrategy,
    MostRestrictiveStrategy,
    PreferProfileStrategy,
    get_strategy,
    list_strategies,
)
from .visualizer import DiffVisualizer


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
        ValueError: If fewer than 2 profiles provided.

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


__all__ = [
    "CSVReportGenerator",
    "ComparisonResult",
    "ComparisonStatistics",
    "ConflictResolution",
    "DiffType",
    "DiffVisualizer",
    "EntityDiff",
    "FieldDiff",
    "FirstWinsStrategy",
    "HTMLReportGenerator",
    "LastWinsStrategy",
    "LeastRestrictiveStrategy",
    "MarkdownReportGenerator",
    "MergeResult",
    "MergeStrategy",
    "MergeWarning",
    "MostRestrictiveStrategy",
    "PreferProfileStrategy",
    "ReportGenerator",
    "SpecComparator",
    "SpecMerger",
    "compare",
    "get_strategy",
    "list_strategies",
    "merge",
]
