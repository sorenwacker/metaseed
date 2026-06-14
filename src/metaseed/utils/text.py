"""Text utilities for metaseed."""

import re


def to_snake_case(name: str) -> str:
    """Convert CamelCase or PascalCase to snake_case.

    Args:
        name: Name in CamelCase or PascalCase (e.g., "BiologicalMaterial").

    Returns:
        Name in snake_case (e.g., "biological_material").
    """
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
