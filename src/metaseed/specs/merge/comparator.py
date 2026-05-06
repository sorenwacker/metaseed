"""N-way profile specification comparator.

This module provides functionality to compare multiple profile specifications
and identify differences in entities, fields, constraints, and metadata.
"""

import logging
from typing import Self

from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    ProfileSpec,
    ValidationRuleSpec,
)

from .models import (
    ComparisonResult,
    ComparisonStatistics,
    DiffType,
    EntityDiff,
    FieldDiff,
)

logger = logging.getLogger(__name__)


class SpecComparator:
    """Compares N profile specifications.

    Loads profiles via SpecLoader and performs detailed comparison of
    entities, fields, constraints, and validation rules.
    """

    def __init__(self: Self, loader: SpecLoader | None = None) -> None:
        """Initialize the comparator.

        Args:
            loader: Optional SpecLoader instance. Creates new one if not provided.
        """
        self._loader = loader or SpecLoader()

    def compare(self: Self, profiles: list[tuple[str, str]]) -> ComparisonResult:
        """Compare N profile specifications or explore a single profile.

        Args:
            profiles: List of (profile_name, version) tuples to compare.
                Example: [("miappe", "1.1"), ("isa", "1.0")]
                With a single profile, returns an "explore" result with all
                entities/fields marked as UNCHANGED (structure visualization only).

        Returns:
            ComparisonResult with detailed differences.

        Raises:
            ValueError: If no profiles provided.
        """
        if len(profiles) < 1:
            raise ValueError("At least 1 profile required")

        # Single profile = explore mode (no comparison)
        if len(profiles) == 1:
            return self._explore_single(profiles[0])

        logger.info("Comparing %d profiles: %s", len(profiles), profiles)

        # Load all profiles
        profile_specs: dict[str, ProfileSpec] = {}
        profile_ids: list[str] = []

        for profile_name, version in profiles:
            profile_id = f"{profile_name}/{version}"
            profile_ids.append(profile_id)
            logger.debug("Loading profile: %s", profile_id)
            profile_specs[profile_id] = self._loader.load_profile(
                version=version, profile=profile_name
            )

        result = ComparisonResult(
            profiles=profile_ids,
            profile_specs=profile_specs,
        )

        # Compare profile metadata
        result.metadata_diffs = self._compare_metadata(profile_specs)

        # Compare entities
        result.entity_diffs = self._compare_entities(profile_specs)

        # Compare validation rules
        result.validation_rule_diffs = self._compare_validation_rules(profile_specs)

        # Calculate statistics
        result.statistics = self._calculate_statistics(result)

        logger.info(
            "Comparison complete: %d entities (%d common, %d conflicts)",
            result.statistics.total_entities,
            result.statistics.common_entities,
            result.statistics.conflicting_fields,
        )

        return result

    def _explore_single(self: Self, profile: tuple[str, str]) -> ComparisonResult:
        """Load single profile for exploration (no diff).

        Args:
            profile: Tuple of (profile_name, version).

        Returns:
            ComparisonResult with all entities/fields marked as UNCHANGED.
        """
        profile_name, version = profile
        profile_id = f"{profile_name}/{version}"

        logger.info("Exploring single profile: %s", profile_id)

        spec = self._loader.load_profile(version=version, profile=profile_name)

        # Create entity diffs with all UNCHANGED status
        entity_diffs: list[EntityDiff] = []
        for entity_name, entity_def in spec.entities.items():
            field_diffs = [
                FieldDiff(
                    field_name=f.name,
                    diff_type=DiffType.UNCHANGED,
                    profiles={profile_id: f},
                    attributes_changed=[],
                    values={},
                )
                for f in entity_def.fields
            ]
            entity_diffs.append(
                EntityDiff(
                    entity_name=entity_name,
                    diff_type=DiffType.UNCHANGED,
                    profiles={profile_id: True},
                    field_diffs=field_diffs,
                    ontology_term_diff=False,
                    description_diff=False,
                )
            )

        # Calculate statistics for single profile
        stats = ComparisonStatistics(
            total_entities=len(entity_diffs),
            common_entities=len(entity_diffs),
            unique_entities=0,
            modified_entities=0,
            total_fields=sum(len(ed.field_diffs) for ed in entity_diffs),
            common_fields=sum(len(ed.field_diffs) for ed in entity_diffs),
            modified_fields=0,
            conflicting_fields=0,
        )

        logger.info(
            "Explore complete: %d entities, %d fields", stats.total_entities, stats.total_fields
        )

        return ComparisonResult(
            profiles=[profile_id],
            profile_specs={profile_id: spec},
            entity_diffs=entity_diffs,
            validation_rule_diffs={},
            metadata_diffs={},
            statistics=stats,
        )

    def _compare_metadata(
        self: Self, profile_specs: dict[str, ProfileSpec]
    ) -> dict[str, dict[str, str | None]]:
        """Compare profile metadata across profiles.

        Args:
            profile_specs: Mapping of profile ID to ProfileSpec.

        Returns:
            Dictionary of metadata field -> profile values.
        """
        metadata_fields = ["name", "display_name", "description", "ontology", "root_entity"]
        diffs: dict[str, dict[str, str | None]] = {}

        for field_name in metadata_fields:
            values: dict[str, str | None] = {}
            for profile_id, spec in profile_specs.items():
                values[profile_id] = getattr(spec, field_name, None)

            # Only include if values differ
            unique_values = {str(v) for v in values.values() if v is not None}
            if len(unique_values) > 1:
                diffs[field_name] = values

        return diffs

    def _compare_entities(self: Self, profile_specs: dict[str, ProfileSpec]) -> list[EntityDiff]:
        """Compare entities across all profiles.

        Args:
            profile_specs: Mapping of profile ID to ProfileSpec.

        Returns:
            List of EntityDiff objects.
        """
        # Collect all entity names (case-insensitive dedup)
        all_entities: dict[str, str] = {}  # lowercase -> original case
        for spec in profile_specs.values():
            for entity_name in spec.entities:
                key = entity_name.lower()
                if key not in all_entities:
                    all_entities[key] = entity_name

        entity_diffs: list[EntityDiff] = []

        for entity_key, entity_name in sorted(all_entities.items()):
            # Check which profiles have this entity
            entity_presence: dict[str, bool] = {}
            entity_specs: dict[str, EntityDefSpec] = {}

            for profile_id, spec in profile_specs.items():
                # Case-insensitive entity lookup
                found = False
                for name, entity_def in spec.entities.items():
                    if name.lower() == entity_key:
                        entity_presence[profile_id] = True
                        entity_specs[profile_id] = entity_def
                        found = True
                        break
                if not found:
                    entity_presence[profile_id] = False

            # Determine entity diff type (base-relative)
            # First profile is the base/reference
            all_profile_ids = list(profile_specs.keys())
            base_profile = all_profile_ids[0]
            in_base = entity_presence.get(base_profile, False)
            in_others = any(v for pid, v in entity_presence.items() if pid != base_profile)

            if in_base and in_others:
                diff_type = DiffType.UNCHANGED
            elif in_base and not in_others:
                # Only in base - removed in compare profile
                diff_type = DiffType.REMOVED
            elif not in_base and in_others:
                # Not in base - added in compare profile
                diff_type = DiffType.ADDED
            else:
                diff_type = DiffType.REMOVED

            # Compare entity attributes
            ontology_diff = self._values_differ(
                {pid: es.ontology_term for pid, es in entity_specs.items()}
            )
            description_diff = self._values_differ(
                {pid: es.description for pid, es in entity_specs.items()}
            )

            # Compare fields within entity
            field_diffs = self._compare_fields(entity_specs, list(profile_specs.keys()))

            # If entity exists in all profiles but fields differ, it's modified
            if diff_type == DiffType.UNCHANGED and (
                ontology_diff
                or description_diff
                or any(fd.diff_type != DiffType.UNCHANGED for fd in field_diffs)
            ):
                diff_type = DiffType.MODIFIED

            entity_diffs.append(
                EntityDiff(
                    entity_name=entity_name,
                    diff_type=diff_type,
                    profiles=entity_presence,
                    field_diffs=field_diffs,
                    ontology_term_diff=ontology_diff,
                    description_diff=description_diff,
                )
            )

        return entity_diffs

    def _compare_fields(
        self: Self,
        entity_specs: dict[str, EntityDefSpec],
        all_profile_ids: list[str],
    ) -> list[FieldDiff]:
        """Compare fields across entity definitions.

        Args:
            entity_specs: Mapping of profile ID to EntityDefSpec.
            all_profile_ids: List of all profile IDs being compared.

        Returns:
            List of FieldDiff objects.
        """
        # Collect all field names
        all_fields: dict[str, str] = {}  # lowercase -> original
        field_by_profile: dict[str, dict[str, FieldSpec]] = {}

        for profile_id, entity_def in entity_specs.items():
            field_by_profile[profile_id] = {}
            for field_spec in entity_def.fields:
                key = field_spec.name.lower()
                if key not in all_fields:
                    all_fields[key] = field_spec.name
                field_by_profile[profile_id][key] = field_spec

        field_diffs: list[FieldDiff] = []

        for field_key, field_name in sorted(all_fields.items()):
            # Get field from each profile that has the entity
            field_specs: dict[str, FieldSpec | None] = {}
            for profile_id in all_profile_ids:
                if profile_id in entity_specs:
                    field_specs[profile_id] = field_by_profile.get(profile_id, {}).get(field_key)
                else:
                    field_specs[profile_id] = None

            # Determine diff type and changed attributes
            diff_type, attributes_changed, values = self._analyze_field_diff(
                field_specs, all_profile_ids
            )

            field_diffs.append(
                FieldDiff(
                    field_name=field_name,
                    diff_type=diff_type,
                    profiles=field_specs,
                    attributes_changed=attributes_changed,
                    values=values,
                )
            )

        return field_diffs

    def _analyze_field_diff(
        self: Self,
        field_specs: dict[str, FieldSpec | None],
        all_profile_ids: list[str],
    ) -> tuple[DiffType, list[str], dict[str, dict[str, object]]]:
        """Analyze differences in a field across profiles.

        The first profile in all_profile_ids is treated as the base/reference.
        - REMOVED: Field in base but not in other profiles
        - ADDED: Field not in base but in other profiles
        - UNCHANGED: Field same in all profiles
        - MODIFIED: Field differs between profiles

        Args:
            field_specs: Mapping of profile ID to FieldSpec or None.
            all_profile_ids: List of all profile IDs (first is base).

        Returns:
            Tuple of (diff_type, attributes_changed, values_by_profile).
        """
        base_profile = all_profile_ids[0]
        base_spec = field_specs.get(base_profile)
        other_specs = {k: v for k, v in field_specs.items() if k != base_profile}

        # Check presence relative to base
        in_base = base_spec is not None
        in_others = any(v is not None for v in other_specs.values())

        if not in_base and not in_others:
            return DiffType.REMOVED, [], {}

        if not in_base and in_others:
            # Field only in other profiles (added relative to base)
            return DiffType.ADDED, [], {}

        if in_base and not in_others:
            # Field only in base (removed in other profiles)
            return DiffType.REMOVED, [], {}

        # Field exists in base - check if it's in all other profiles
        present_specs = {k: v for k, v in field_specs.items() if v is not None}
        if len(present_specs) < len(all_profile_ids):
            # Field missing from some profiles
            return DiffType.MODIFIED, [], {}

        # Field exists in all profiles - compare attributes
        attributes_to_compare = [
            "type",
            "required",
            "description",
            "ontology_term",
            "items",
            "parent_ref",
            "unique_within",
            "reference",
        ]

        changed_attrs: list[str] = []
        values: dict[str, dict[str, object]] = {}
        has_conflict = False

        for attr in attributes_to_compare:
            attr_values: dict[str, object] = {}
            for profile_id, spec in present_specs.items():
                attr_values[profile_id] = getattr(spec, attr, None)

            unique_values = {str(v) for v in attr_values.values()}
            if len(unique_values) > 1:
                changed_attrs.append(attr)
                values[attr] = attr_values
                # Conflicts occur when important attributes differ
                if attr in ["type", "required", "items"]:
                    has_conflict = True

        # Compare constraints
        constraint_diff = self._compare_constraints(
            {pid: spec.constraints for pid, spec in present_specs.items()}
        )
        if constraint_diff:
            changed_attrs.append("constraints")
            values["constraints"] = constraint_diff

        if has_conflict:
            return DiffType.CONFLICT, changed_attrs, values
        if changed_attrs:
            return DiffType.MODIFIED, changed_attrs, values
        return DiffType.UNCHANGED, [], {}

    def _compare_constraints(
        self: Self, constraints: dict[str, Constraints | None]
    ) -> dict[str, dict[str, object]] | None:
        """Compare constraints across profiles.

        Args:
            constraints: Mapping of profile ID to Constraints or None.

        Returns:
            Dictionary of differing constraint attributes, or None if same.
        """
        constraint_attrs = [
            "pattern",
            "min_length",
            "max_length",
            "minimum",
            "maximum",
            "min_items",
            "max_items",
            "enum",
        ]

        diffs: dict[str, dict[str, object]] = {}

        for attr in constraint_attrs:
            values: dict[str, object] = {}
            for profile_id, constraint in constraints.items():
                if constraint is None:
                    values[profile_id] = None
                else:
                    values[profile_id] = getattr(constraint, attr, None)

            unique = {str(v) for v in values.values()}
            if len(unique) > 1:
                diffs[attr] = values

        return diffs or None

    def _compare_validation_rules(
        self: Self, profile_specs: dict[str, ProfileSpec]
    ) -> dict[str, dict[str, ValidationRuleSpec | None]]:
        """Compare validation rules across profiles.

        Args:
            profile_specs: Mapping of profile ID to ProfileSpec.

        Returns:
            Dictionary of rule name -> profile values.
        """
        # Collect all rule names
        all_rules: set[str] = set()
        rules_by_profile: dict[str, dict[str, ValidationRuleSpec]] = {}

        for profile_id, spec in profile_specs.items():
            rules_by_profile[profile_id] = {}
            for rule in spec.validation_rules:
                all_rules.add(rule.name)
                rules_by_profile[profile_id][rule.name] = rule

        diffs: dict[str, dict[str, ValidationRuleSpec | None]] = {}

        for rule_name in sorted(all_rules):
            values: dict[str, ValidationRuleSpec | None] = {}
            for profile_id in profile_specs:
                values[profile_id] = rules_by_profile.get(profile_id, {}).get(rule_name)

            # Only include if rules differ across profiles
            present_count = sum(1 for v in values.values() if v is not None)
            if present_count != len(profile_specs):
                diffs[rule_name] = values

        return diffs

    def _values_differ(self: Self, values: dict[str, object]) -> bool:
        """Check if values differ across a dictionary.

        Args:
            values: Dictionary of identifier to value.

        Returns:
            True if values differ, False if all same.
        """
        unique = {str(v) for v in values.values() if v is not None}
        return len(unique) > 1

    def _calculate_statistics(self: Self, result: ComparisonResult) -> ComparisonStatistics:
        """Calculate summary statistics for a comparison.

        Args:
            result: ComparisonResult to analyze.

        Returns:
            ComparisonStatistics with counts.
        """
        stats = ComparisonStatistics()
        stats.total_entities = len(result.entity_diffs)

        for ed in result.entity_diffs:
            # Entity statistics
            if all(ed.profiles.get(p, False) for p in result.profiles):
                stats.common_entities += 1
            elif sum(1 for v in ed.profiles.values() if v) == 1:
                stats.unique_entities += 1

            if ed.diff_type in [DiffType.MODIFIED, DiffType.CONFLICT]:
                stats.modified_entities += 1

            # Field statistics
            stats.total_fields += len(ed.field_diffs)
            for fd in ed.field_diffs:
                if fd.diff_type == DiffType.UNCHANGED:
                    stats.common_fields += 1
                elif fd.diff_type == DiffType.CONFLICT:
                    stats.conflicting_fields += 1
                elif fd.diff_type == DiffType.MODIFIED:
                    stats.modified_fields += 1

        return stats
