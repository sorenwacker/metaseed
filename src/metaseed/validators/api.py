"""Validation entry-point functions.

The public ``validate`` / ``validate_entity`` / ``validate_entity_with_report``
helpers, re-exported from :mod:`metaseed.validators`.
"""

import logging
from typing import Any

from pydantic import BaseModel

from metaseed.utils import to_snake_case
from metaseed.validators.base import ValidationCheck, ValidationError, has_value
from metaseed.validators.engine import create_engine_for_entity

logger = logging.getLogger(__name__)


def _pydantic_constraint_errors(
    data: dict[str, Any], entity_spec: Any
) -> list[ValidationError]:
    """Return Pydantic constraint errors for an entity's simple fields.

    Builds the spec's Pydantic model from the entity's non-nested fields and
    collects type/pattern/range/length/enum violations. Missing-required errors
    are skipped here — the engine's RequiredFieldsRule reports those, so this
    avoids duplicates. Shared by every public validation path so they enforce
    the same constraints.

    Args:
        data: Entity data dictionary.
        entity_spec: The loaded entity spec.

    Returns:
        List of constraint validation errors (empty if none).
    """
    from pydantic import ValidationError as PydanticValidationError

    from metaseed.models.factory import create_model_from_spec

    errors: list[ValidationError] = []
    try:
        model_class = create_model_from_spec(entity_spec)
        nested_field_names = {
            f.name for f in entity_spec.fields if f.type.value == "list" and f.items
        }
        simple_data = {
            key: value
            for key, value in data.items()
            if key not in nested_field_names and not key.startswith("_")
        }
        model_class(**simple_data)
    except PydanticValidationError as e:
        for err in e.errors():
            if err["type"] == "missing":
                continue
            field_path = ".".join(str(loc) for loc in err["loc"])
            errors.append(
                ValidationError(field=field_path, message=err["msg"], rule="constraint")
            )
    return errors


def _validate_nested(
    data: dict[str, Any],
    entity: str,
    version: str,
    profile: str = "miappe",
    path: str = "",
) -> list[ValidationError]:
    """Recursively validate data and nested entities.

    Args:
        data: Dictionary to validate.
        entity: Entity type name.
        version: Profile version.
        profile: Profile name.
        path: Current path for error reporting.

    Returns:
        List of all validation errors including nested ones.
    """
    from metaseed.specs.loader import SpecLoader, SpecLoadError

    errors: list[ValidationError] = []

    # Validate current entity
    engine = create_engine_for_entity(entity, version, profile=profile)
    for error in engine.validate(data):
        # Prefix field with path for nested errors
        error_field = f"{path}.{error.field}" if path else error.field
        errors.append(
            ValidationError(field=error_field, message=error.message, rule=error.rule)
        )

    # Find and validate nested list fields
    loader = SpecLoader(profile=profile)
    try:
        spec = loader.load_entity(entity, version)
    except (FileNotFoundError, KeyError, ValueError, SpecLoadError) as e:
        # Entity spec not found - return errors collected so far
        logger.debug("Could not load entity spec %s: %s", entity, e)
        return errors

    # Pydantic constraint validation (types/patterns/ranges/enums) for this entity.
    for error in _pydantic_constraint_errors(data, spec):
        error_field = f"{path}.{error.field}" if path else error.field
        errors.append(
            ValidationError(field=error_field, message=error.message, rule=error.rule)
        )

    for field in spec.fields:
        if field.type.value == "list" and field.items:
            items = data.get(field.name, [])
            if not items:
                continue

            # Check if items is a known entity type
            item_entity = to_snake_case(field.items)
            try:
                loader.load_entity(item_entity, version)
            except (FileNotFoundError, KeyError, ValueError, SpecLoadError):
                # Not a known entity type, skip nested validation
                continue

            # Validate each item in the list
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    item_path = (
                        f"{path}.{field.name}[{i}]" if path else f"{field.name}[{i}]"
                    )
                    errors.extend(
                        _validate_nested(item, item_entity, version, profile, item_path)
                    )

    return errors


def validate(
    data: dict[str, Any] | BaseModel,
    entity: str | None = None,
    version: str = "1.2",
    profile: str = "miappe",
    cascade: bool = True,
) -> list[ValidationError]:
    """Validate data against entity rules.

    Supports both dict and Pydantic model instances. When cascade=True,
    recursively validates nested entities.

    Args:
        data: Dictionary or Pydantic model to validate.
        entity: Entity name (e.g., "investigation"). Auto-detected from
            model class name if data is a BaseModel and entity is None.
        version: Profile version.
        profile: Profile name (e.g., "miappe", "isa").
        cascade: If True, recursively validate nested entities.

    Returns:
        List of validation errors. Empty if validation passes.

    Example:
        >>> # Validate a dict
        >>> errors = validate({"unique_id": "INV001"}, "investigation")

        >>> # Validate a model instance (entity auto-detected)
        >>> inv = Investigation(unique_id="INV001", title="Test")
        >>> errors = validate(inv)

        >>> # Cascade validation to nested entities
        >>> inv.studies.append(Study(unique_id="STU001", title="Study"))
        >>> errors = validate(inv, cascade=True)
    """
    # Handle Pydantic model instances
    if isinstance(data, BaseModel):
        if entity is None:
            entity = to_snake_case(data.__class__.__name__)
        data = data.model_dump(mode="json")

    if entity is None:
        raise ValueError("entity must be specified when data is a dict")

    if cascade:
        return _validate_nested(data, entity, version, profile)

    engine = create_engine_for_entity(entity, version, profile=profile)
    errors: list[ValidationError] = list(engine.validate(data))
    from metaseed.specs.loader import SpecLoader, SpecLoadError

    try:
        spec = SpecLoader(profile=profile).load_entity(entity, version)
    except (FileNotFoundError, KeyError, ValueError, SpecLoadError):
        return errors
    errors.extend(_pydantic_constraint_errors(data, spec))
    return errors


def validate_entity(
    data: dict[str, Any],
    entity_type: str,
    profile: str = "miappe",
    version: str = "1.2",
) -> list[ValidationError]:
    """Validate an entity with comprehensive checks.

    Combines Pydantic model validation (type checking, constraints like
    patterns, min/max length, numeric ranges) with custom validation rules
    from the profile spec (date_range, coordinate_pair, etc.).

    This is the canonical validation function that both UI and MCP should use.

    Args:
        data: Entity data dictionary to validate.
        entity_type: Entity type name (e.g., "Investigation", "Study").
        profile: Profile name (e.g., "miappe", "isa").
        version: Profile version.

    Returns:
        List of validation errors. Empty if validation passes.

    Example:
        >>> errors = validate_entity(
        ...     {"unique_id": "INV001", "title": "Test"},
        ...     entity_type="Investigation",
        ...     profile="miappe",
        ...     version="1.2",
        ... )
    """
    from metaseed.specs.loader import SpecLoader, SpecLoadError

    errors: list[ValidationError] = []
    loader = SpecLoader(profile=profile)

    try:
        entity_spec = loader.load_entity(entity_type, version)
    except (FileNotFoundError, SpecLoadError) as e:
        errors.append(
            ValidationError(
                field=entity_type,
                message=f"Unknown entity type: {entity_type} - {e}",
                rule="error",
            )
        )
        return errors

    # 1. Pydantic validation - checks types, patterns, ranges, etc.
    errors.extend(_pydantic_constraint_errors(data, entity_spec))

    # 2. Custom rule validation from profile spec
    engine = create_engine_for_entity(entity_type, version, profile=profile)
    errors.extend(engine.validate(data))

    return errors


def validate_entity_with_report(
    data: dict[str, Any],
    entity_type: str,
    profile: str = "miappe",
    version: str = "1.2",
) -> list[ValidationCheck]:
    """Validate an entity and return detailed check results.

    Like validate_entity(), but returns both passed and failed checks
    for comprehensive reporting. Skips checks for empty optional fields.

    Combines Pydantic model validation (type checking, constraints) with
    custom validation rules from the profile spec.

    Args:
        data: Entity data dictionary to validate.
        entity_type: Entity type name (e.g., "Investigation", "Study").
        profile: Profile name (e.g., "miappe", "isa").
        version: Profile version.

    Returns:
        List of ValidationCheck instances showing all checks performed.

    Example:
        >>> checks = validate_entity_with_report(
        ...     {"unique_id": "INV001", "title": "Test"},
        ...     entity_type="Investigation",
        ...     profile="miappe",
        ...     version="1.2",
        ... )
        >>> for check in checks:
        ...     print(f"{check.field}: {check.check} - {'PASS' if check.passed else 'FAIL'}")
    """
    from pydantic import ValidationError as PydanticValidationError

    from metaseed.models.factory import create_model_from_spec
    from metaseed.specs.loader import SpecLoader, SpecLoadError

    checks: list[ValidationCheck] = []
    loader = SpecLoader(profile=profile)

    try:
        entity_spec = loader.load_entity(entity_type, version)
    except (FileNotFoundError, SpecLoadError) as e:
        checks.append(
            ValidationCheck(
                field=entity_type,
                check="load_spec",
                passed=False,
                message=f"Unknown entity type: {entity_type} - {e}",
            )
        )
        return checks

    # Build set of required fields and optional fields with values
    required_fields = {f.name for f in entity_spec.get_required_fields()}
    optional_fields_with_values = {
        f.name for f in entity_spec.fields if not f.required and has_value(data, f.name)
    }
    fields_to_check = required_fields | optional_fields_with_values

    # Get nested field names (to exclude from Pydantic validation)
    nested_field_names = {
        f.name for f in entity_spec.fields if f.type.value == "list" and f.items
    }

    # 1. Pydantic validation - checks types, patterns, ranges, etc.
    try:
        model_class = create_model_from_spec(entity_spec)

        simple_data = {
            key: value
            for key, value in data.items()
            if key not in nested_field_names and not key.startswith("_")
        }

        model_class(**simple_data)

        # All Pydantic checks passed - record them
        for field in entity_spec.fields:
            if field.name in nested_field_names:
                continue
            if field.name not in fields_to_check:
                continue

            # Record type check pass
            checks.append(
                ValidationCheck(
                    field=field.name,
                    check="type",
                    passed=True,
                )
            )

            # Record constraint checks if applicable
            if field.constraints:
                if field.constraints.pattern:
                    checks.append(
                        ValidationCheck(
                            field=field.name,
                            check="pattern",
                            passed=True,
                        )
                    )
                if field.constraints.min_length is not None:
                    checks.append(
                        ValidationCheck(
                            field=field.name,
                            check="min_length",
                            passed=True,
                        )
                    )
                if field.constraints.max_length is not None:
                    checks.append(
                        ValidationCheck(
                            field=field.name,
                            check="max_length",
                            passed=True,
                        )
                    )
                if field.constraints.minimum is not None:
                    checks.append(
                        ValidationCheck(
                            field=field.name,
                            check="minimum",
                            passed=True,
                        )
                    )
                if field.constraints.maximum is not None:
                    checks.append(
                        ValidationCheck(
                            field=field.name,
                            check="maximum",
                            passed=True,
                        )
                    )
                if field.constraints.enum:
                    checks.append(
                        ValidationCheck(
                            field=field.name,
                            check="enum",
                            passed=True,
                        )
                    )

    except PydanticValidationError as e:
        # Record failed checks from Pydantic errors
        failed_fields: set[str] = set()
        for err in e.errors():
            field_path = ".".join(str(loc) for loc in err["loc"])
            failed_fields.add(field_path)
            checks.append(
                ValidationCheck(
                    field=field_path,
                    check="constraint",
                    passed=False,
                    message=err["msg"],
                )
            )

        # Record passed checks for fields that didn't fail
        for field in entity_spec.fields:
            if field.name in nested_field_names:
                continue
            if field.name not in fields_to_check:
                continue
            if field.name in failed_fields:
                continue

            checks.append(
                ValidationCheck(
                    field=field.name,
                    check="type",
                    passed=True,
                )
            )

    # 2. Custom rule validation from profile spec
    engine = create_engine_for_entity(entity_type, version, profile=profile)
    checks.extend(engine.validate_with_report(data))

    return checks
