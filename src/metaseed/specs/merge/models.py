"""Data models for spec comparison and merge operations.

This module defines the core data structures for comparing and merging
profile specifications.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from metaseed.specs.schema import FieldSpec, ProfileSpec


class DiffType(StrEnum):
    """Type of difference found between profiles."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass
class FieldDiff:
    """Difference in a field across profiles.

    Attributes:
        field_name: Name of the field being compared.
        diff_type: Type of difference (added, removed, modified, etc.).
        profiles: Mapping of profile identifier to field spec or None.
        attributes_changed: List of attribute names that differ.
        base_value: Original value in the base profile (if applicable).
        values: Mapping of profile identifier to attribute values that differ.
    """

    field_name: str
    diff_type: DiffType
    profiles: dict[str, FieldSpec | None] = field(default_factory=dict)
    attributes_changed: list[str] = field(default_factory=list)
    base_value: Any = None
    values: dict[str, Any] = field(default_factory=dict)

    @property
    def is_conflict(self) -> bool:
        """Check if this field has conflicting values across profiles."""
        return self.diff_type == DiffType.CONFLICT

    def get_profile_value(self, profile_id: str, attribute: str) -> Any:
        """Get a specific attribute value for a profile.

        Args:
            profile_id: Profile identifier (e.g., "miappe/1.1").
            attribute: Attribute name (e.g., "required", "type").

        Returns:
            The attribute value or None if not found.
        """
        field_spec = self.profiles.get(profile_id)
        if field_spec is None:
            return None
        return getattr(field_spec, attribute, None)


@dataclass
class EntityDiff:
    """Difference in an entity across profiles.

    Attributes:
        entity_name: Name of the entity being compared.
        diff_type: Type of difference for the entity itself.
        profiles: Mapping of profile identifier to whether entity exists.
        field_diffs: List of field differences within this entity.
        ontology_term_diff: Whether ontology_term differs.
        description_diff: Whether description differs.
    """

    entity_name: str
    diff_type: DiffType
    profiles: dict[str, bool] = field(default_factory=dict)
    field_diffs: list[FieldDiff] = field(default_factory=list)
    ontology_term_diff: bool = False
    description_diff: bool = False

    @property
    def has_conflicts(self) -> bool:
        """Check if any fields have conflicts."""
        return any(fd.is_conflict for fd in self.field_diffs)

    @property
    def common_fields(self) -> list[FieldDiff]:
        """Get fields that exist in all profiles."""
        return [fd for fd in self.field_diffs if fd.diff_type == DiffType.UNCHANGED]

    @property
    def modified_fields(self) -> list[FieldDiff]:
        """Get fields that have modifications."""
        return [fd for fd in self.field_diffs if fd.diff_type == DiffType.MODIFIED]

    @property
    def conflicting_fields(self) -> list[FieldDiff]:
        """Get fields with conflicts."""
        return [fd for fd in self.field_diffs if fd.diff_type == DiffType.CONFLICT]


@dataclass
class ComparisonStatistics:
    """Statistics for a profile comparison.

    Attributes:
        total_entities: Total unique entities across all profiles.
        common_entities: Entities present in all profiles.
        unique_entities: Entities present in only one profile.
        modified_entities: Entities with differences.
        total_fields: Total unique fields across all entities.
        common_fields: Fields present in all profiles.
        modified_fields: Fields with differences.
        conflicting_fields: Fields with conflicting values.
    """

    total_entities: int = 0
    common_entities: int = 0
    unique_entities: int = 0
    modified_entities: int = 0
    total_fields: int = 0
    common_fields: int = 0
    modified_fields: int = 0
    conflicting_fields: int = 0


@dataclass
class ComparisonResult:
    """Complete comparison result for N profiles.

    Attributes:
        profiles: List of profile identifiers compared.
        profile_specs: Mapping of profile identifier to ProfileSpec.
        entity_diffs: List of entity differences.
        validation_rule_diffs: Differences in validation rules.
        metadata_diffs: Differences in profile metadata.
        statistics: Summary statistics for the comparison.
    """

    profiles: list[str] = field(default_factory=list)
    profile_specs: dict[str, ProfileSpec] = field(default_factory=dict)
    entity_diffs: list[EntityDiff] = field(default_factory=list)
    validation_rule_diffs: dict[str, Any] = field(default_factory=dict)
    metadata_diffs: dict[str, dict[str, Any]] = field(default_factory=dict)
    statistics: ComparisonStatistics = field(default_factory=ComparisonStatistics)

    @property
    def common_entities(self) -> list[str]:
        """Get entity names present in all profiles."""
        return [
            ed.entity_name
            for ed in self.entity_diffs
            if all(ed.profiles.get(p, False) for p in self.profiles)
        ]

    @property
    def conflicting_fields(self) -> list[FieldDiff]:
        """Get all conflicting fields across all entities."""
        conflicts = []
        for ed in self.entity_diffs:
            conflicts.extend(ed.conflicting_fields)
        return conflicts

    def get_entity_diff(self, entity_name: str) -> EntityDiff | None:
        """Get diff for a specific entity.

        Args:
            entity_name: Name of the entity.

        Returns:
            EntityDiff or None if not found.
        """
        for ed in self.entity_diffs:
            if ed.entity_name.lower() == entity_name.lower():
                return ed
        return None

    def entities_unique_to(self, profile_id: str) -> list[str]:
        """Get entities that only exist in a specific profile.

        Args:
            profile_id: Profile identifier.

        Returns:
            List of entity names unique to that profile.
        """
        unique = []
        for ed in self.entity_diffs:
            if ed.profiles.get(profile_id, False):
                # Check if other profiles don't have it
                other_have = any(
                    ed.profiles.get(p, False) for p in self.profiles if p != profile_id
                )
                if not other_have:
                    unique.append(ed.entity_name)
        return unique


@dataclass
class ConflictResolution:
    """Manual resolution for a conflict.

    Attributes:
        entity_name: Entity containing the conflict.
        field_name: Field with the conflict.
        attribute: Attribute that was in conflict (e.g., "required", "type").
        resolved_value: The value to use for resolution.
        source_profile: Profile the value was taken from, or None if custom.
    """

    entity_name: str
    field_name: str
    attribute: str
    resolved_value: Any
    source_profile: str | None = None


@dataclass
class MergeWarning:
    """Warning generated during merge operation.

    Attributes:
        entity_name: Entity where warning occurred.
        field_name: Field where warning occurred (optional).
        message: Warning message.
        resolution_applied: Description of automatic resolution applied.
    """

    entity_name: str
    field_name: str | None
    message: str
    resolution_applied: str | None = None


@dataclass
class MergeResult:
    """Result of merging profiles.

    Attributes:
        merged_profile: The merged ProfileSpec.
        source_profiles: List of profile identifiers that were merged.
        strategy_used: Name of the merge strategy applied.
        resolutions_applied: List of conflict resolutions applied.
        warnings: List of warnings generated during merge.
        unresolved_conflicts: Conflicts that could not be automatically resolved.
    """

    merged_profile: ProfileSpec
    source_profiles: list[str] = field(default_factory=list)
    strategy_used: str = ""
    resolutions_applied: list[ConflictResolution] = field(default_factory=list)
    warnings: list[MergeWarning] = field(default_factory=list)
    unresolved_conflicts: list[FieldDiff] = field(default_factory=list)

    @property
    def has_unresolved_conflicts(self) -> bool:
        """Check if there are unresolved conflicts."""
        return len(self.unresolved_conflicts) > 0

    def to_yaml(self) -> str:
        """Export merged profile as YAML string.

        Returns:
            YAML representation of the merged profile.
        """
        import yaml

        return yaml.dump(
            self.merged_profile.model_dump(mode="json", exclude_none=True),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    def to_dict(self) -> dict[str, Any]:
        """Export merged profile as dictionary.

        Returns:
            Dictionary representation of the merged profile.
        """
        return self.merged_profile.model_dump(mode="json", exclude_none=True)
