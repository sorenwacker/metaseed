"""Validation engine for running multiple rules.

This module provides the validation engine that coordinates rule execution.
"""

import re
from typing import Any, Self

from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import (
    FieldSpec,
    FieldType,
    ProfileSpec,
    ValidationRuleSpec,
)
from metaseed.validators.base import ValidationCheck, ValidationError, ValidationRule
from metaseed.validators.rules import (
    ConditionalRule,
    CoordinatePairRule,
    DateRangeRule,
    ListCardinalityRule,
    PatternRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
)

# Field types whose rule-level ``pattern`` the model factory cannot enforce via a
# Pydantic pattern (uri -> AnyUrl; ontology_term). For these the engine adds a
# PatternRule; string patterns are already merged onto the field (see
# ``loader._merge_rule_constraints_into_fields``).
_ENGINE_PATTERN_TYPES = frozenset({FieldType.URI, FieldType.ONTOLOGY_TERM})


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

    def validate_with_report(self: Self, data: dict[str, Any]) -> list[ValidationCheck]:
        """Run all rules and return detailed check results.

        Unlike validate(), this returns both passed and failed checks,
        allowing for comprehensive reporting.

        Args:
            data: Dictionary to validate.

        Returns:
            List of ValidationCheck instances for all checks performed.
        """
        checks: list[ValidationCheck] = []
        for rule in self.rules:
            errors = rule.validate(data)
            rule_name = rule.name

            if errors:
                for error in errors:
                    checks.append(
                        ValidationCheck(
                            field=error.field,
                            check=rule_name,
                            passed=False,
                            message=error.message,
                        )
                    )
            else:
                # Rule passed - determine which field(s) were checked
                fields = self._get_rule_fields(rule)
                for field in fields:
                    checks.append(
                        ValidationCheck(
                            field=field,
                            check=rule_name,
                            passed=True,
                            message=None,
                        )
                    )
        return checks

    def _get_rule_fields(self: Self, rule: ValidationRule) -> list[str]:
        """Get field names that a rule applies to.

        Args:
            rule: The validation rule.

        Returns:
            List of field names the rule validates.
        """
        # Check for common field attributes on rules
        if hasattr(rule, "fields"):
            # RequiredFieldsRule has fields attribute
            return list(rule.fields)
        if hasattr(rule, "field"):
            # Single-field rules like UniqueIdPatternRule
            return [rule.field]
        if hasattr(rule, "start_field") and hasattr(rule, "end_field"):
            # DateRangeRule
            return [rule.start_field, rule.end_field]
        if hasattr(rule, "lat_field") and hasattr(rule, "lon_field"):
            # CoordinatePairRule
            return [rule.lat_field, rule.lon_field]
        if hasattr(rule, "_fields"):
            # ConditionalRule extracts fields from condition
            return list(rule._fields)
        return []


# The explicit `type:` values a validation rule may declare. Kept in sync with
# the documented list in ValidationRuleSpec and _create_rule_by_type's branches.
# A rule that sets `type:` to anything outside this set is a spec error (e.g. a
# typo like "unique" for "uniqueness") and is rejected loudly rather than being
# silently dropped, which would let the rule never run and invalid data pass.
_VALID_RULE_TYPES = frozenset(
    {
        "conditional",
        "date_range",
        "coordinate_pair",
        "cardinality",
        "uniqueness",
        "reference",
    }
)


def _create_rule_by_type(
    rule_spec: ValidationRuleSpec,
) -> ValidationRule | None:
    """Create a rule based on explicit type field.

    Args:
        rule_spec: The rule specification.

    Returns:
        A ValidationRule instance, or None for a declared type that this engine
        does not enforce (see the ``uniqueness`` and ``reference`` branches).
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
            if rule_spec.condition and (
                ">=" in rule_spec.condition or "<=" in rule_spec.condition
            ):
                parts = (
                    rule_spec.condition.replace(">=", " ").replace("<=", " ").split()
                )
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

    # A uniqueness or reference rule is a question about the records around
    # this one - siblings sharing a value, an identifier defined elsewhere -
    # and this engine only ever sees one record. Both are enforced over the
    # whole tree by DatasetValidator (_validate_uniqueness, _validate_
    # references), which reads the rule spec directly. Building an engine rule
    # here would produce one that can never fire.
    return None


def _infer_rule_type(
    rule_spec: ValidationRuleSpec,
) -> ValidationRule | None:
    """Infer rule type from fields (backward compatibility).

    Args:
        rule_spec: The rule specification.

    Returns:
        A ValidationRule instance, or None if type cannot be inferred or is
        enforced elsewhere.
    """
    # Skip rules handled by Pydantic constraints (these are documented in the spec
    # but shouldn't create engine rules)
    if rule_spec.pattern and rule_spec.field:
        return None  # Handled by Pydantic pattern constraint

    if (
        rule_spec.minimum is not None or rule_spec.maximum is not None
    ) and rule_spec.field:
        return None  # Handled by Pydantic ge/le constraints

    if rule_spec.enum and rule_spec.field:
        return None  # Handled by Pydantic Literal types

    # Cardinality rules
    if (
        rule_spec.min_items is not None or rule_spec.max_items is not None
    ) and rule_spec.field:
        return ListCardinalityRule(
            field=rule_spec.field,
            min_items=rule_spec.min_items,
            max_items=rule_spec.max_items,
            rule_name=rule_spec.name,
            message=rule_spec.message,
        )

    # Uniqueness and reference rules span records, so they are enforced by
    # DatasetValidator over the whole tree, not here (see _create_rule_by_type).
    if (rule_spec.unique_within or rule_spec.reference) and rule_spec.field:
        return None

    # Conditional rules
    if rule_spec.condition:
        # Handle special cases first
        if "latitude" in rule_spec.condition and "longitude" in rule_spec.condition:
            # Coordinate pair rule: read the actual field names out of the
            # condition rather than assuming a fixed prefix. This makes the rule
            # target the real fields for any entity (material_source_latitude,
            # biological_material_latitude, a bare latitude, ...) instead of
            # silently validating nonexistent lat/lon fields.
            tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rule_spec.condition)
            lat_field = next((t for t in tokens if t.endswith("latitude")), "latitude")
            lon_field = next(
                (t for t in tokens if t.endswith("longitude")), "longitude"
            )
            return CoordinatePairRule(
                lat_field=lat_field,
                lon_field=lon_field,
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
) -> ValidationRule | None:
    """Create a ValidationRule instance from a ValidationRuleSpec.

    Args:
        rule_spec: The rule specification from the YAML.

    Returns:
        A ValidationRule instance, or None if the rule is enforced somewhere
        other than this engine.

    Note:
        If `type` field is set, uses explicit type creation.
        Otherwise, infers type from other fields (backward compatibility).

        The following rule types are handled by Pydantic constraints
        and return None:
        - Pattern rules (Pydantic pattern constraint)
        - Numeric range rules (Pydantic ge/le constraints)
        - Enum rules (Pydantic Literal types)

        Uniqueness and reference rules also return None: they span records and
        are enforced by DatasetValidator.
    """
    # Explicit type takes precedence
    if rule_spec.type:
        if rule_spec.type not in _VALID_RULE_TYPES:
            valid = ", ".join(sorted(_VALID_RULE_TYPES))
            raise ValueError(
                f"Validation rule '{rule_spec.name}' has unknown type "
                f"'{rule_spec.type}'. Valid types are: {valid}."
            )
        return _create_rule_by_type(rule_spec)

    # Legacy: infer from fields (backward compatibility)
    return _infer_rule_type(rule_spec)


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


def _profile_rules_for_entity(
    entity: str,
    profile_spec: ProfileSpec,
) -> list[ValidationRule]:
    """Build the rules a profile declares for one entity.

    Args:
        entity: Entity name (e.g., "Investigation").
        profile_spec: The loaded profile specification.

    Returns:
        One ValidationRule per declared rule that applies to the entity and is
        not already enforced as a Pydantic constraint.
    """
    entity_lower = entity.lower()
    entity_def = next(
        (e for n, e in profile_spec.entities.items() if n.lower() == entity_lower),
        None,
    )
    field_types = {f.name: f.type for f in entity_def.fields} if entity_def else {}

    rules: list[ValidationRule] = []
    for rule_spec in profile_spec.validation_rules:
        if not _applies_to_entity(rule_spec, entity):
            continue
        # A pattern on a uri/ontology_term field can't be a Pydantic
        # constraint, so enforce it here rather than let it silently drop.
        if (
            rule_spec.pattern
            and rule_spec.field
            and field_types.get(rule_spec.field) in _ENGINE_PATTERN_TYPES
        ):
            rules.append(
                PatternRule(
                    field=rule_spec.field,
                    pattern=rule_spec.pattern,
                    message=rule_spec.message or rule_spec.description or None,
                )
            )
            continue
        rule = _create_rule_from_spec(rule_spec)
        if rule:
            rules.append(rule)
    return rules


def _child_collection_fields(entity: str, profile_spec: ProfileSpec) -> set[str]:
    """Field names on ``entity`` that hold child entities rather than values.

    Args:
        entity: Entity name (e.g., "Investigation").
        profile_spec: The loaded profile specification.

    Returns:
        The names of list fields whose ``items`` is another entity of the
        profile. Empty if the profile does not define the entity.
    """
    entity_lower = entity.lower()
    entity_def = next(
        (e for n, e in profile_spec.entities.items() if n.lower() == entity_lower),
        None,
    )
    if entity_def is None:
        return set()

    entity_names = {name.lower() for name in profile_spec.entities}
    return {
        f.name
        for f in entity_def.fields
        if f.type == FieldType.LIST and f.items and f.items.lower() in entity_names
    }


def create_engine_for_extracted_record(
    entity: str,
    profile_spec: ProfileSpec,
) -> ValidationEngine:
    """Create an engine for a single extracted record.

    An extracted record is one source row mapped onto an entity: it is flat,
    its child entities are extracted as records of their own, and the records
    around it are not visible. Only the profile rules that such a record can
    answer are added, because a rule that cannot see its data does not pass -
    it reports every record as bad.

    Excluded here, on top of what no engine enforces (``uniqueness`` and
    ``reference``, which span records and belong to ``DatasetValidator``):

    - ``cardinality`` over a child collection: the children are separate
      records, so the parent never holds them and the count is always zero.
    - Rules derived from the entity spec rather than declared by the profile
      (required fields, identifier patterns): ``ExtractionContext`` reports
      missing required fields itself.

    Args:
        entity: Entity name (e.g., "Investigation").
        profile_spec: The loaded profile specification the record belongs to.

    Returns:
        Configured ValidationEngine instance, empty if the profile declares no
        applicable rule for the entity.
    """
    child_collections = _child_collection_fields(entity, profile_spec)
    engine = ValidationEngine()

    for rule in _profile_rules_for_entity(entity, profile_spec):
        if isinstance(rule, ListCardinalityRule) and rule.field in child_collections:
            continue
        engine.add_rule(rule)

    return engine


def _declared_pattern(
    field_name: str, entity: str, profile_spec: ProfileSpec | None
) -> ValidationRuleSpec | None:
    """The profile's own pattern rule for a field, if it declares one."""
    if profile_spec is None:
        return None
    for rule_spec in profile_spec.validation_rules:
        if (
            rule_spec.pattern
            and rule_spec.field == field_name
            and _applies_to_entity(rule_spec, entity)
        ):
            return rule_spec
    return None


def _identifier_rule(
    field: FieldSpec, entity: str, profile_spec: ProfileSpec | None
) -> ValidationRule | None:
    """How this profile's identifier field is checked.

    The default — alphanumerics, underscores and hyphens — is MIAPPE's, and was
    applied to every field named ``identifier`` or ``unique_id`` in every
    profile, chosen by name. A DiSSCo specimen is identified by a DOI, which
    contains ``:`` and ``/``, so the profile's own pattern and the imposed one
    could not both be satisfied and no valid specimen could be created (#246).

    Where the profile or the field states what its identifier looks like, that
    statement is enforced instead. Where nothing is stated, the default stands:
    an identifier with a space in it breaks every reference that names it.

    Returns:
        The rule to add, or ``None`` when the declared pattern is already
        enforced elsewhere and adding it here would report it twice.
    """
    declared = _declared_pattern(field.name, entity, profile_spec)
    if declared is not None:
        if field.type in _ENGINE_PATTERN_TYPES:
            # Already added by _profile_rules_for_entity.
            return None
        return PatternRule(
            field=field.name,
            pattern=declared.pattern or "",
            message=declared.message or declared.description or None,
        )

    own = getattr(field.constraints, "pattern", None) if field.constraints else None
    if own:
        return PatternRule(field=field.name, pattern=own)

    return UniqueIdPatternRule(field=field.name)


def create_engine_for_entity(
    entity: str,
    version: str = "1.2",
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

    # Load the profile first: what it declares about a field decides whether
    # the identifier default below applies at all.
    profile_spec = None
    try:
        profile_spec = loader.load_profile(version, profile)
        entity_lower = entity.lower()
        profile_entities = [e.lower() for e in profile_spec.entities]
        if entity_lower in profile_entities:
            entity_found = True
    except SpecLoadError:
        # If profile not found, continue with basic rules only
        pass

    # Load entity spec for required fields
    try:
        spec = loader.load_entity(entity, version, profile)
        entity_found = True

        # Add required fields rule
        required_fields = [f.name for f in spec.get_required_fields()]
        if required_fields:
            engine.add_rule(RequiredFieldsRule(fields=required_fields))

        for field in spec.fields:
            if field.name in ("unique_id", "identifier"):
                rule = _identifier_rule(field, entity, profile_spec)
                if rule is not None:
                    engine.add_rule(rule)
                break
    except SpecLoadError:
        # Entity spec not found, check if profile has this entity
        pass

    if profile_spec is not None:
        for rule in _profile_rules_for_entity(entity, profile_spec):
            engine.add_rule(rule)

    # Raise error if entity was not found in either spec or profile
    if not entity_found:
        raise SpecLoadError(f"Entity not found: {entity} ({profile} v{version})")

    return engine
