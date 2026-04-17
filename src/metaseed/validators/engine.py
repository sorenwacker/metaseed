"""Validation engine for running multiple rules.

This module provides the validation engine that coordinates rule execution.
"""

from typing import Any, Self

from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import ValidationRuleSpec
from metaseed.validators.base import ValidationError, ValidationRule
from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    ListCardinalityRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
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


def _create_rule_from_spec(rule_spec: ValidationRuleSpec) -> ValidationRule | None:
    """Create a ValidationRule instance from a ValidationRuleSpec.

    Args:
        rule_spec: The rule specification from the YAML.

    Returns:
        A ValidationRule instance, or None if rule type not supported.

    Note:
        The following rule types are now handled by Pydantic constraints
        and are skipped here:
        - Pattern rules (Pydantic pattern constraint)
        - Numeric range rules (Pydantic ge/le constraints)
        - Enum rules (Pydantic Literal types)
        - Cardinality rules (Pydantic min_length/max_length on lists)
    """
    # Skip rules now handled by Pydantic constraints
    if rule_spec.pattern and rule_spec.field:
        return None  # Handled by Pydantic pattern constraint

    if (rule_spec.minimum is not None or rule_spec.maximum is not None) and rule_spec.field:
        return None  # Handled by Pydantic ge/le constraints

    if rule_spec.enum and rule_spec.field:
        return None  # Handled by Pydantic Literal types

    if (rule_spec.min_items is not None or rule_spec.max_items is not None) and rule_spec.field:
        return ListCardinalityRule(
            field=rule_spec.field,
            min_items=rule_spec.min_items,
            max_items=rule_spec.max_items,
            rule_name=rule_spec.name,
        )

    # Conditional rules
    if rule_spec.condition:
        # Handle special cases first
        if "latitude" in rule_spec.condition and "longitude" in rule_spec.condition:
            # Coordinate pair rule
            # Extract field names from condition
            if "biological_material_latitude" in rule_spec.condition:
                return CoordinatePairRule(
                    lat_field="biological_material_latitude",
                    lon_field="biological_material_longitude",
                    rule_name=rule_spec.name,
                )
            return CoordinatePairRule(
                lat_field="latitude",
                lon_field="longitude",
                rule_name=rule_spec.name,
            )

        # Handle date comparison conditions
        if ">=" in rule_spec.condition or "<=" in rule_spec.condition:
            # Date range or comparison rule
            parts = rule_spec.condition.replace(">=", " ").replace("<=", " ").split()
            if len(parts) == 2:
                if ">=" in rule_spec.condition:
                    # end_date >= start_date means start must be before end
                    return DateRangeRule(
                        start_field=parts[1],
                        end_field=parts[0],
                    )
                return DateRangeRule(
                    start_field=parts[0],
                    end_field=parts[1],
                )

        # General conditional rule
        return ConditionalRule(
            condition=rule_spec.condition,
            rule_name=rule_spec.name,
        )

    # Reference rules are handled separately (need context of available IDs)
    # Uniqueness rules are handled separately (need context of all entities)

    return None


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
) -> ValidationEngine:
    """Create a validation engine configured for a specific entity.

    Loads the entity spec and profile validation rules, configuring
    appropriate validation rules based on both.

    Args:
        entity: Entity name (e.g., "Investigation").
        version: Profile version (e.g., "1.1").
        profile: Profile name (e.g., "miappe", "combined").

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
    except Exception:
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
                    rule = _create_rule_from_spec(rule_spec)
                    if rule:
                        engine.add_rule(rule)
    except Exception:
        # If profile not found, continue with basic rules only
        pass

    # Raise error if entity was not found in either spec or profile
    if not entity_found:
        from metaseed.specs.loader import SpecLoadError

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
    except Exception:
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
