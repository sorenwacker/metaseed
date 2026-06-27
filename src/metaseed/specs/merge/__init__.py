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

from .comparator import SpecComparator
from .facade import compare, merge
from .merger import SpecMerger
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
