"""Validation engine for running multiple rules.

This module provides the validation engine that coordinates rule execution.
"""

from typing import Any, Self

from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import ValidationRuleSpec
from metaseed.validators.base import ValidationError, ValidationRule
from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    EntityReferenceRule,
    ListCardinalityRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
    UniquenessRule,
)


class ValidationEngine:
    """Engine for running validation rules.

    Collects and runs validation rules against data, aggregating all
    errors from all rules.
    """

    def __init__(self: Self) -> None:
        """Initialize the engine with an empty rule list."""
        self.rules: list[ValidationRule] = []

    def add_rule(self: Self, rule: ValidationRule) -> Self:
        """Add a validation rule to the engine.

        Args:
            rule: Validation rule to add.

        Returns:
            Self for chaining.
        """
        self.rules.append(rule)
        return self

    def validate(self: Self, data: dict[str, Any]) -> list[ValidationError]:
        """Run all rules against the data.

        Args:
            data: Dictionary to validate.

        Returns:
            List of all validation errors from all rules.
        """
        errors: list[ValidationError] = []
        for rule in self.rules:
            errors.extend(rule.validate(data))
        return errors


def _create_rule_by_type(
    rule_spec: ValidationRuleSpec,
    available_refs: dict[str, set[str]] | None = None,
) -> ValidationRule | None:
    """Create a rule based on explicit type field.

    Args:
        rule_spec: The rule specification.
        available_refs: Optional dict of entity -> available IDs for reference rules.

    Returns:
        A ValidationRule instance, or None if type not recognized.
    """
    rule_type = rule_spec.type

    if rule_type == "conditional":
        if not rule_spec.condition:
            return None
        return ConditionalRule(
            condition=rule_spec.condition,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    if rule_type == "date_range":
        # Use explicit fields if provided, else parse from condition
        start_field = rule_spec.start_field
        end_field = rule_spec.end_field
        if not start_field or not end_field:
            # Try to parse from condition
            if rule_spec.condition and (">=" in rule_spec.condition or "<=" in rule_spec.condition):
                parts = rule_spec.condition.replace(">=", " ").replace("<=", " ").split()
                if len(parts) == 2:
                    if ">=" in rule_spec.condition:
                        start_field = parts[1]
                        end_field = parts[0]
                    else:
                        start_field = parts[0]
                        end_field = parts[1]
        if not start_field or not end_field:
            return None
        return DateRangeRule(
            start_field=start_field,
            end_field=end_field,
            message=rule_spec.message,
        )

    if rule_type == "coordinate_pair":
        lat_field = rule_spec.lat_field or "latitude"
        lon_field = rule_spec.lon_field or "longitude"
        return CoordinatePairRule(
            lat_field=lat_field,
            lon_field=lon_field,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    if rule_type == "cardinality":
        if not rule_spec.field:
            return None
        return ListCardinalityRule(
            field=rule_spec.field,
            min_items=rule_spec.min_items,
            max_items=rule_spec.max_items,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    if rule_type == "uniqueness":
        if not rule_spec.field:
            return None
        return UniquenessRule(
            field=rule_spec.field,
            scope=rule_spec.unique_within or "parent",
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    if rule_type == "reference":
        if not rule_spec.field or not rule_spec.reference:
            return None
        # Parse Entity.field reference
        parts = rule_spec.reference.split(".")
        if len(parts) != 2:
            return None
        target_entity, target_field = parts
        # Get available IDs from context
        ids = available_refs.get(target_entity, set()) if available_refs else set()
        return EntityReferenceRule(
            field=rule_spec.field,
            reference_id_field=target_field,
            available_ids=ids,
            message=rule_spec.message,
        )

    return None


def _infer_rule_type(
    rule_spec: ValidationRuleSpec,
    available_refs: dict[str, set[str]] | None = None,
) -> ValidationRule | None:
    """Infer rule type from fields (backward compatibility).

    Args:
        rule_spec: The rule specification.
        available_refs: Optional dict of entity -> available IDs for reference rules.

    Returns:
        A ValidationRule instance, or None if type cannot be inferred.
    """
    # Skip rules handled by Pydantic constraints (these are documented in the spec
    # but shouldn't create engine rules)
    if rule_spec.pattern and rule_spec.field:
        return None  # Handled by Pydantic pattern constraint

    if (rule_spec.minimum is not None or rule_spec.maximum is not None) and rule_spec.field:
        return None  # Handled by Pydantic ge/le constraints

    if rule_spec.enum and rule_spec.field:
        return None  # Handled by Pydantic Literal types

    # Cardinality rules
    if (rule_spec.min_items is not None or rule_spec.max_items is not None) and rule_spec.field:
        return ListCardinalityRule(
            field=rule_spec.field,
            min_items=rule_spec.min_items,
            max_items=rule_spec.max_items,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    # Uniqueness rules
    if rule_spec.unique_within and rule_spec.field:
        return UniquenessRule(
            field=rule_spec.field,
            scope=rule_spec.unique_within,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    # Reference rules
    if rule_spec.reference and rule_spec.field:
        parts = rule_spec.reference.split(".")
        if len(parts) == 2:
            target_entity, target_field = parts
            ids = available_refs.get(target_entity, set()) if available_refs else set()
            return EntityReferenceRule(
                field=rule_spec.field,
                reference_id_field=target_field,
                available_ids=ids,
                message=rule_spec.message,
            )

    # Conditional rules
    if rule_spec.condition:
        # Handle special cases first
        if "latitude" in rule_spec.condition and "longitude" in rule_spec.condition:
            # Coordinate pair rule - extract field names
            if "biological_material_latitude" in rule_spec.condition:
                return CoordinatePairRule(
                    lat_field="biological_material_latitude",
                    lon_field="biological_material_longitude",
                    rule_name=rule_spec.name,
                    message=rule_spec.message,
                )
            return CoordinatePairRule(
                lat_field="latitude",
                lon_field="longitude",
                rule_name=rule_spec.name,
                message=rule_spec.message,
            )

        # Handle date comparison conditions
        if ">=" in rule_spec.condition or "<=" in rule_spec.condition:
            parts = rule_spec.condition.replace(">=", " ").replace("<=", " ").split()
            if len(parts) == 2:
                if ">=" in rule_spec.condition:
                    return DateRangeRule(
                        start_field=parts[1],
                        end_field=parts[0],
                        message=rule_spec.message,
                    )
                return DateRangeRule(
                    start_field=parts[0],
                    end_field=parts[1],
                    message=rule_spec.message,
                )

        # General conditional rule
        return ConditionalRule(
            condition=rule_spec.condition,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    return None


def _create_rule_from_spec(
    rule_spec: ValidationRuleSpec,
    available_refs: dict[str, set[str]] | None = None,
) -> ValidationRule | None:
    """Create a ValidationRule instance from a ValidationRuleSpec.

    Args:
        rule_spec: The rule specification from the YAML.
        available_refs: Optional dict mapping entity names to sets of available IDs.
            Used for reference validation rules.

    Returns:
        A ValidationRule instance, or None if rule type not supported.

    Note:
        If `type` field is set, uses explicit type creation.
        Otherwise, infers type from other fields (backward compatibility).

        The following rule types are handled by Pydantic constraints
        and return None:
        - Pattern rules (Pydantic pattern constraint)
        - Numeric range rules (Pydantic ge/le constraints)
        - Enum rules (Pydantic Literal types)
    """
    # Explicit type takes precedence
    if rule_spec.type:
        return _create_rule_by_type(rule_spec, available_refs)

    # Legacy: infer from fields (backward compatibility)
    return _infer_rule_type(rule_spec, available_refs)


def _applies_to_entity(rule_spec: ValidationRuleSpec, entity: str) -> bool:
    """Check if a rule applies to a specific entity.

    Args:
        rule_spec: The rule specification.
        entity: Entity name to check (case-insensitive).

    Returns:
        True if rule applies to this entity.
    """
    applies_to = rule_spec.applies_to
    entity_lower = entity.lower()

    if applies_to == "all":
        return True

    if isinstance(applies_to, list):
        return any(e.lower() == entity_lower for e in applies_to)

    return applies_to.lower() == entity_lower


def create_engine_for_entity(
    entity: str,
    version: str = "1.1",
    profile: str = "miappe",
    available_refs: dict[str, set[str]] | None = None,
) -> ValidationEngine:
    """Create a validation engine configured for a specific entity.

    Loads the entity spec and profile validation rules, configuring
    appropriate validation rules based on both.

    Args:
        entity: Entity name (e.g., "Investigation").
        version: Profile version (e.g., "1.1").
        profile: Profile name (e.g., "miappe", "combined").
        available_refs: Optional dict mapping entity names to sets of available IDs.
            Used for reference validation rules. If not provided, reference rules
            will use empty ID sets.

    Returns:
        Configured ValidationEngine instance.
    """
    loader = SpecLoader()
    engine = ValidationEngine()
    entity_found = False

    # Load entity spec for required fields
    try:
        spec = loader.load_entity(entity, version, profile)
        entity_found = True

        # Add required fields rule
        required_fields = [f.name for f in spec.get_required_fields()]
        if required_fields:
            engine.add_rule(RequiredFieldsRule(fields=required_fields))

        # Add ID pattern rule for identifier/unique_id fields
        for field in spec.fields:
            if field.name in ("unique_id", "identifier"):
                engine.add_rule(UniqueIdPatternRule(field=field.name))
                break
    except SpecLoadError:
        # Entity spec not found, check if profile has this entity
        pass

    # Load profile validation rules
    try:
        profile_spec = loader._load_profile(version, profile)
        if profile_spec:
            # Check if entity exists in profile
            entity_lower = entity.lower()
            profile_entities = [e.lower() for e in profile_spec.entities]
            if entity_lower in profile_entities:
                entity_found = True

            for rule_spec in profile_spec.validation_rules:
                if _applies_to_entity(rule_spec, entity):
                    rule = _create_rule_from_spec(rule_spec, available_refs)
                    if rule:
                        engine.add_rule(rule)
    except SpecLoadError:
        # If profile not found, continue with basic rules only
        pass

    # Raise error if entity was not found in either spec or profile
    if not entity_found:
        raise SpecLoadError(f"Entity not found: {entity} ({profile} v{version})")

    return engine


def create_engine_from_profile(
    version: str = "1.1",
    profile: str = "miappe",
) -> dict[str, ValidationEngine]:
    """Create validation engines for all entities in a profile.

    Args:
        version: Profile version (e.g., "1.1").
        profile: Profile name (e.g., "miappe", "combined").

    Returns:
        Dictionary mapping entity names to configured ValidationEngine instances.
    """
    loader = SpecLoader()
    engines: dict[str, ValidationEngine] = {}

    try:
        entities = loader.list_entities(version, profile)
        for entity in entities:
            engines[entity] = create_engine_for_entity(entity, version, profile)
    except SpecLoadError:
        pass

    return engines


def validate(
    data: dict[str, Any],
    entity: str,
    version: str = "1.1",
    profile: str = "miappe",
) -> list[ValidationError]:
    """Validate data against entity rules.

    Convenience function that creates an engine and validates in one call.

    Args:
        data: Dictionary to validate.
        entity: Entity name (e.g., "Investigation").
        version: Profile version.
        profile: Profile name.

    Returns:
        List of validation errors.
    """
    engine = create_engine_for_entity(entity, version, profile)
    return engine.validate(data)
