"""Tests for metaseed.utils.text helpers."""

from metaseed.utils import to_snake_case


def test_pascal_case_to_snake_case() -> None:
    """PascalCase names convert to snake_case."""
    assert to_snake_case("BiologicalMaterial") == "biological_material"


def test_single_word_lowercased() -> None:
    """Single words are lowercased without separators."""
    assert to_snake_case("Investigation") == "investigation"


def test_acronym_boundaries() -> None:
    """Trailing acronyms get a separator before them."""
    assert to_snake_case("studyID") == "study_id"
