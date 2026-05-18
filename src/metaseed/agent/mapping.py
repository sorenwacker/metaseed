"""Column-to-field mapping logic for metadata extraction.

This module provides types and functions for mapping source file columns
to entity fields based on name similarity and type compatibility.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Self

from pydantic import BaseModel, Field

from metaseed.specs.schema import EntitySpec


class FieldMapping(BaseModel):
    """Mapping from a source column to an entity field.

    Attributes:
        field_name: Name of the target field in the entity.
        source_column: Name of the source column (None if not mapped).
        confidence: Confidence score for the mapping (0.0 to 1.0).
        default_value: Default value to use if source_column is None.
        notes: Optional notes about the mapping.
    """

    field_name: str
    source_column: str | None = None
    confidence: float = 0.0
    default_value: str | None = None
    notes: str | None = None


class ColumnMapping(BaseModel):
    """Complete mapping configuration for extracting an entity.

    Attributes:
        entity_name: Name of the target entity.
        fields: List of field mappings.
        source_table: Name or index of the source table.
    """

    entity_name: str
    fields: list[FieldMapping] = Field(default_factory=list)
    source_table: str | int | None = None

    def get_field_mapping(self: Self, field_name: str) -> FieldMapping | None:
        """Get mapping for a specific field."""
        for mapping in self.fields:
            if mapping.field_name == field_name:
                return mapping
        return None

    def set_field_mapping(
        self: Self,
        field_name: str,
        source_column: str | None = None,
        confidence: float = 1.0,
        default_value: str | None = None,
    ) -> None:
        """Set or update mapping for a field."""
        for mapping in self.fields:
            if mapping.field_name == field_name:
                mapping.source_column = source_column
                mapping.confidence = confidence
                mapping.default_value = default_value
                return

        self.fields.append(
            FieldMapping(
                field_name=field_name,
                source_column=source_column,
                confidence=confidence,
                default_value=default_value,
            )
        )


def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    Converts to lowercase, removes special characters, and splits
    camelCase/snake_case/kebab-case.

    Args:
        name: Name to normalize.

    Returns:
        Normalized name as space-separated words.
    """
    # Insert space before capitals (for camelCase)
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Replace separators with spaces
    name = re.sub(r"[-_.]", " ", name)
    # Remove non-alphanumeric except spaces
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    # Normalize whitespace
    name = " ".join(name.split()).lower()
    return name


def compute_similarity(name1: str, name2: str) -> float:
    """Compute similarity score between two names.

    Uses normalized names and SequenceMatcher for fuzzy matching.

    Args:
        name1: First name.
        name2: Second name.

    Returns:
        Similarity score from 0.0 to 1.0.
    """
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    # Exact match after normalization
    if norm1 == norm2:
        return 1.0

    # Check if one contains the other
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if words1 and words2:
        overlap = len(words1 & words2) / max(len(words1), len(words2))
        if overlap > 0.5:
            return 0.7 + (overlap * 0.2)

    # Fuzzy match
    return SequenceMatcher(None, norm1, norm2).ratio()


def suggest_mapping(
    source_columns: list[str],
    entity_spec: EntitySpec,
    threshold: float = 0.5,
) -> list[FieldMapping]:
    """Suggest column-to-field mappings based on name similarity.

    For each field in the entity spec, finds the best matching column
    from the source and creates a FieldMapping if the similarity exceeds
    the threshold.

    Args:
        source_columns: List of column names from the source.
        entity_spec: Entity specification to map to.
        threshold: Minimum similarity score to suggest mapping.

    Returns:
        List of suggested FieldMappings, one per entity field.
    """
    mappings: list[FieldMapping] = []
    used_columns: set[str] = set()

    # Sort fields by required status (required first)
    sorted_fields = sorted(entity_spec.fields, key=lambda f: (not f.required, f.name))

    for field in sorted_fields:
        best_match: str | None = None
        best_score = 0.0

        # Try to match against unused columns
        for column in source_columns:
            if column in used_columns:
                continue

            # Compute similarity
            score = compute_similarity(field.name, column)

            # Also check against codename if available
            if field.codename:
                codename_score = compute_similarity(field.codename, column)
                score = max(score, codename_score)

            if score > best_score:
                best_score = score
                best_match = column

        # Create mapping
        if best_match and best_score >= threshold:
            mappings.append(
                FieldMapping(
                    field_name=field.name,
                    source_column=best_match,
                    confidence=best_score,
                    notes=f"Matched column '{best_match}' with {best_score:.0%} confidence",
                )
            )
            used_columns.add(best_match)
        else:
            # Create unmapped entry
            notes = "No matching column found"
            if field.required:
                notes += " (required field)"
            mappings.append(
                FieldMapping(
                    field_name=field.name,
                    source_column=None,
                    confidence=0.0,
                    notes=notes,
                )
            )

    return mappings


def create_mapping(
    entity_name: str,
    field_mappings: list[FieldMapping],
    source_table: str | int | None = None,
) -> ColumnMapping:
    """Create a ColumnMapping from field mappings.

    Args:
        entity_name: Name of the target entity.
        field_mappings: List of field mappings.
        source_table: Optional source table identifier.

    Returns:
        ColumnMapping instance.
    """
    return ColumnMapping(
        entity_name=entity_name,
        fields=field_mappings,
        source_table=source_table,
    )


def mapping_to_dict(mapping: ColumnMapping) -> dict:
    """Convert ColumnMapping to a simple dictionary format.

    Args:
        mapping: The column mapping.

    Returns:
        Dictionary representation.
    """
    return {
        "entity": mapping.entity_name,
        "source_table": mapping.source_table,
        "fields": {
            fm.field_name: {
                "column": fm.source_column,
                "confidence": fm.confidence,
                "default": fm.default_value,
            }
            for fm in mapping.fields
        },
    }


def mapping_from_dict(data: dict) -> ColumnMapping:
    """Create ColumnMapping from dictionary.

    Args:
        data: Dictionary with entity, source_table, and fields.

    Returns:
        ColumnMapping instance.
    """
    fields = []
    for field_name, field_data in data.get("fields", {}).items():
        fields.append(
            FieldMapping(
                field_name=field_name,
                source_column=field_data.get("column"),
                confidence=field_data.get("confidence", 1.0),
                default_value=field_data.get("default"),
            )
        )

    return ColumnMapping(
        entity_name=data.get("entity", ""),
        fields=fields,
        source_table=data.get("source_table"),
    )
