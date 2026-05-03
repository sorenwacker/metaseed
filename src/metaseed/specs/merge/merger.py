"""Profile specification merger.

This module provides functionality to merge multiple profile specifications
with configurable conflict resolution strategies.
"""

import logging
from typing import Self

from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import (
    EntityDefSpec,
    FieldSpec,
    ProfileSpec,
    ValidationRuleSpec,
)

from .comparator import SpecComparator
from .models import (
    ConflictResolution,
    DiffType,
    FieldDiff,
    MergeResult,
    MergeWarning,
)
from .strategies import MergeStrategy, get_strategy

logger = logging.getLogger(__name__)


class SpecMerger:
    """Merges multiple profile specifications.

    Uses a comparator to find differences and a strategy to resolve conflicts.
    Supports manual conflict resolutions override.
    """

    def __init__(
        self: Self,
        loader: SpecLoader | None = None,
        comparator: SpecComparator | None = None,
    ) -> None:
        """Initialize the merger.

        Args:
            loader: Optional SpecLoader instance.
            comparator: Optional SpecComparator instance.
        """
        self._loader = loader or SpecLoader()
        self._comparator = comparator or SpecComparator(self._loader)

    def merge(
        self: Self,
        profiles: list[tuple[str, str]],
        strategy: str | MergeStrategy = "first_wins",
        output_name: str = "merged",
        output_version: str = "1.0",
        manual_resolutions: list[ConflictResolution] | None = None,
    ) -> MergeResult:
        """Merge multiple profile specifications.

        Args:
            profiles: List of (profile_name, version) tuples to merge.
            strategy: Merge strategy name or MergeStrategy instance.
            output_name: Name for the merged profile.
            output_version: Version for the merged profile.
            manual_resolutions: Optional manual conflict resolutions.

        Returns:
            MergeResult with merged profile and metadata.

        Raises:
            ValueError: If fewer than 2 profiles provided.
        """
        if len(profiles) < 2:
            raise ValueError("At least 2 profiles required for merge")

        logger.info(
            "Merging %d profiles with strategy '%s': %s",
            len(profiles),
            strategy if isinstance(strategy, str) else strategy.name,
            profiles,
        )

        # Resolve strategy
        merge_strategy = get_strategy(strategy) if isinstance(strategy, str) else strategy

        # Compare profiles
        comparison = self._comparator.compare(profiles)
        profile_order = comparison.profiles

        # Build resolution lookup
        resolution_map = self._build_resolution_map(manual_resolutions or [])

        # Merge the profiles
        merged_entities: dict[str, EntityDefSpec] = {}
        warnings: list[MergeWarning] = []
        resolutions_applied: list[ConflictResolution] = []
        unresolved: list[FieldDiff] = []

        for entity_diff in comparison.entity_diffs:
            # Include entity if present in any profile
            if not any(entity_diff.profiles.values()):
                continue

            merged_fields, entity_warnings, entity_resolutions, entity_unresolved = (
                self._merge_entity_fields(
                    entity_diff.entity_name,
                    entity_diff.field_diffs,
                    profile_order,
                    merge_strategy,
                    resolution_map,
                    comparison.profile_specs,
                )
            )

            warnings.extend(entity_warnings)
            resolutions_applied.extend(entity_resolutions)
            unresolved.extend(entity_unresolved)

            # Get entity metadata from first profile that has it
            ontology_term = None
            description = ""
            example = None

            for profile_id in profile_order:
                if entity_diff.profiles.get(profile_id, False):
                    spec = comparison.profile_specs[profile_id]
                    entity_name = self._find_entity_name(spec, entity_diff.entity_name)
                    if entity_name:
                        entity_def = spec.entities[entity_name]
                        ontology_term = ontology_term or entity_def.ontology_term
                        description = description or entity_def.description
                        example = example or entity_def.example

            merged_entities[entity_diff.entity_name] = EntityDefSpec(
                ontology_term=ontology_term,
                description=description,
                fields=merged_fields,
                example=example,
            )

        # Merge validation rules
        merged_rules = self._merge_validation_rules(comparison.profile_specs, profile_order)

        # Build merged profile metadata
        first_spec = comparison.profile_specs[profile_order[0]]
        merged_profile = ProfileSpec(
            version=output_version,
            name=output_name,
            display_name=output_name.replace("-", " ").title(),
            description=f"Merged from: {', '.join(profile_order)}",
            ontology=first_spec.ontology,
            root_entity=first_spec.root_entity,
            validation_rules=merged_rules,
            entities=merged_entities,
        )

        result = MergeResult(
            merged_profile=merged_profile,
            source_profiles=profile_order,
            strategy_used=merge_strategy.name,
            resolutions_applied=resolutions_applied,
            warnings=warnings,
            unresolved_conflicts=unresolved,
        )

        logger.info(
            "Merge complete: %d entities, %d warnings, %d unresolved conflicts",
            len(merged_entities),
            len(warnings),
            len(unresolved),
        )

        return result

    def _build_resolution_map(
        self: Self, resolutions: list[ConflictResolution]
    ) -> dict[tuple[str, str, str], ConflictResolution]:
        """Build lookup map for manual resolutions.

        Args:
            resolutions: List of manual conflict resolutions.

        Returns:
            Dictionary keyed by (entity, field, attribute).
        """
        return {(r.entity_name.lower(), r.field_name.lower(), r.attribute): r for r in resolutions}

    def _merge_entity_fields(
        self: Self,
        entity_name: str,
        field_diffs: list[FieldDiff],
        profile_order: list[str],
        strategy: MergeStrategy,
        resolution_map: dict[tuple[str, str, str], ConflictResolution],
        _profile_specs: dict[str, ProfileSpec],
    ) -> tuple[
        list[FieldSpec],
        list[MergeWarning],
        list[ConflictResolution],
        list[FieldDiff],
    ]:
        """Merge fields for an entity.

        Args:
            entity_name: Name of the entity.
            field_diffs: List of field differences.
            profile_order: Ordered list of profile IDs.
            strategy: Merge strategy to use.
            resolution_map: Manual resolution lookup.
            profile_specs: Profile specifications.

        Returns:
            Tuple of (merged_fields, warnings, resolutions_applied, unresolved).
        """
        merged_fields: list[FieldSpec] = []
        warnings: list[MergeWarning] = []
        resolutions_applied: list[ConflictResolution] = []
        unresolved: list[FieldDiff] = []

        for field_diff in field_diffs:
            # Skip fields that don't exist in any profile
            if not any(s is not None for s in field_diff.profiles.values()):
                continue

            if field_diff.diff_type == DiffType.CONFLICT:
                # Check for manual resolution
                manual = self._find_manual_resolution(
                    entity_name, field_diff.field_name, resolution_map
                )

                if manual:
                    resolved_spec = self._apply_manual_resolution(field_diff, manual, profile_order)
                    merged_fields.append(resolved_spec)
                    resolutions_applied.extend(manual)
                    warnings.append(
                        MergeWarning(
                            entity_name=entity_name,
                            field_name=field_diff.field_name,
                            message="Conflict resolved via manual resolution",
                            resolution_applied=str([m.attribute for m in manual]),
                        )
                    )
                else:
                    # Use strategy to resolve
                    try:
                        resolved_spec = strategy.resolve_field(field_diff, profile_order)
                        merged_fields.append(resolved_spec)
                        warnings.append(
                            MergeWarning(
                                entity_name=entity_name,
                                field_name=field_diff.field_name,
                                message=f"Conflict resolved via {strategy.name}",
                                resolution_applied=strategy.name,
                            )
                        )
                    except ValueError:
                        unresolved.append(field_diff)

            elif field_diff.diff_type in [DiffType.UNCHANGED, DiffType.MODIFIED]:
                # Use first available spec
                for profile_id in profile_order:
                    spec = field_diff.profiles.get(profile_id)
                    if spec is not None:
                        merged_fields.append(spec)
                        break

            elif field_diff.diff_type == DiffType.ADDED:
                # Include fields that exist in any profile
                for profile_id in profile_order:
                    spec = field_diff.profiles.get(profile_id)
                    if spec is not None:
                        merged_fields.append(spec)
                        warnings.append(
                            MergeWarning(
                                entity_name=entity_name,
                                field_name=field_diff.field_name,
                                message=f"Field added from {profile_id}",
                            )
                        )
                        break

        return merged_fields, warnings, resolutions_applied, unresolved

    def _find_manual_resolution(
        self: Self,
        entity_name: str,
        field_name: str,
        resolution_map: dict[tuple[str, str, str], ConflictResolution],
    ) -> list[ConflictResolution]:
        """Find manual resolutions for a field.

        Args:
            entity_name: Entity name.
            field_name: Field name.
            resolution_map: Resolution lookup.

        Returns:
            List of applicable resolutions.
        """
        resolutions = []
        for key, resolution in resolution_map.items():
            if key[0] == entity_name.lower() and key[1] == field_name.lower():
                resolutions.append(resolution)
        return resolutions

    def _apply_manual_resolution(
        self: Self,
        field_diff: FieldDiff,
        resolutions: list[ConflictResolution],
        profile_order: list[str],
    ) -> FieldSpec:
        """Apply manual resolutions to a field.

        Args:
            field_diff: Field difference.
            resolutions: Manual resolutions to apply.
            profile_order: Profile order.

        Returns:
            Resolved FieldSpec.
        """
        # Start with first available spec
        base_spec: FieldSpec | None = None
        for profile_id in profile_order:
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                base_spec = spec
                break

        if base_spec is None:
            raise ValueError(f"No base spec for {field_diff.field_name}")

        # Apply resolutions
        data = base_spec.model_dump()
        for resolution in resolutions:
            data[resolution.attribute] = resolution.resolved_value

        return FieldSpec.model_validate(data)

    def _merge_validation_rules(
        self: Self,
        profile_specs: dict[str, ProfileSpec],
        profile_order: list[str],
    ) -> list[ValidationRuleSpec]:
        """Merge validation rules from all profiles.

        Args:
            profile_specs: Profile specifications.
            profile_order: Profile order.

        Returns:
            Merged list of validation rules.
        """
        # Collect all rules, dedup by name (first wins)
        rules_by_name: dict[str, ValidationRuleSpec] = {}

        for profile_id in profile_order:
            spec = profile_specs[profile_id]
            for rule in spec.validation_rules:
                if rule.name not in rules_by_name:
                    rules_by_name[rule.name] = rule

        return list(rules_by_name.values())

    def _find_entity_name(self: Self, spec: ProfileSpec, target_name: str) -> str | None:
        """Find entity name in spec (case-insensitive).

        Args:
            spec: Profile spec to search.
            target_name: Entity name to find.

        Returns:
            Actual entity name or None.
        """
        target_lower = target_name.lower()
        for name in spec.entities:
            if name.lower() == target_lower:
                return name
        return None


def merge(
    profiles: list[tuple[str, str]],
    strategy: str = "first_wins",
    output_name: str = "merged",
    output_version: str = "1.0",
    manual_resolutions: list[ConflictResolution] | None = None,
) -> MergeResult:
    """Convenience function to merge profiles.

    Args:
        profiles: List of (profile_name, version) tuples.
        strategy: Merge strategy name.
        output_name: Name for merged profile.
        output_version: Version for merged profile.
        manual_resolutions: Optional manual resolutions.

    Returns:
        MergeResult with merged profile.
    """
    merger = SpecMerger()
    return merger.merge(
        profiles=profiles,
        strategy=strategy,
        output_name=output_name,
        output_version=output_version,
        manual_resolutions=manual_resolutions,
    )
