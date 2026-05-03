"""Validation routes for form validation.

Provides routes for validating form data against profile specs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypedDict

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError as PydanticValidationError
from starlette.requests import Request

from metaseed.facade import ProfileFacade
from metaseed.models import create_model_from_spec
from metaseed.specs.loader import SpecLoader
from metaseed.validators import validate as validate_data

from ..helpers import collect_form_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from metaseed.specs.schema import Constraints

    from ..state import AppState

logger = logging.getLogger(__name__)


class ValidationRule(TypedDict):
    """A validation rule displayed to the user."""

    name: str
    description: str


class ValidationError(TypedDict):
    """A validation error to display to the user."""

    field: str
    message: str
    rule: str


def _describe_constraints(constraints: Constraints) -> list[str]:
    """Build human-readable descriptions of field constraints.

    Args:
        constraints: The field constraints to describe.

    Returns:
        List of constraint descriptions.
    """
    parts = []
    if constraints.min_length is not None:
        parts.append(f"min length: {constraints.min_length}")
    if constraints.max_length is not None:
        parts.append(f"max length: {constraints.max_length}")
    if constraints.minimum is not None:
        parts.append(f"min: {constraints.minimum}")
    if constraints.maximum is not None:
        parts.append(f"max: {constraints.maximum}")
    if constraints.pattern:
        parts.append("pattern")
    if constraints.enum:
        parts.append(f"enum ({len(constraints.enum)} values)")
    return parts


def _get_validation_rules_for_entity(
    entity_type: str, profile: str, version: str
) -> list[ValidationRule]:
    """Get list of validation rules that apply to an entity.

    Args:
        entity_type: Entity name.
        profile: Profile name.
        version: Profile version.

    Returns:
        List of ValidationRule dicts with name and description.
    """
    rules: list[ValidationRule] = []
    loader = SpecLoader(profile=profile)

    # Get entity spec for field constraints
    try:
        entity_spec = loader.load_entity(entity_type, version)

        # Add required fields rule
        required_fields = [f.name for f in entity_spec.get_required_fields()]
        if required_fields:
            rules.append(
                ValidationRule(
                    name=f"{entity_type}: Required fields",
                    description=", ".join(required_fields),
                )
            )

        # Add field constraints
        for field in entity_spec.fields:
            if field.constraints:
                constraint_parts = _describe_constraints(field.constraints)
                if constraint_parts:
                    rules.append(
                        ValidationRule(
                            name=f"{entity_type}.{field.name}",
                            description=", ".join(constraint_parts),
                        )
                    )
    except FileNotFoundError:
        logger.debug("Entity spec not found: %s", entity_type)
    except Exception:
        logger.debug("Failed to load entity spec: %s", entity_type, exc_info=True)

    # Get profile validation rules
    try:
        profile_spec = loader.load_profile(version, profile)
        if profile_spec:
            for rule_spec in profile_spec.validation_rules:
                if _rule_applies_to_entity(rule_spec.applies_to, entity_type):
                    rules.append(
                        ValidationRule(
                            name=f"{entity_type}: {rule_spec.name}",
                            description=rule_spec.description or "Custom validation rule",
                        )
                    )
    except FileNotFoundError:
        logger.debug("Profile spec not found: %s v%s", profile, version)
    except Exception:
        logger.debug("Failed to load profile spec: %s", profile, exc_info=True)

    return rules


def _rule_applies_to_entity(applies_to: str | list[str], entity_type: str) -> bool:
    """Check if a validation rule applies to an entity type.

    Args:
        applies_to: Rule's applies_to value ("all", entity name, or list).
        entity_type: Entity type to check.

    Returns:
        True if the rule applies to this entity.
    """
    entity_lower = entity_type.lower()
    if applies_to == "all":
        return True
    if isinstance(applies_to, list):
        return any(e.lower() == entity_lower for e in applies_to)
    return applies_to.lower() == entity_lower


def _validate_entity_deep(
    values: dict[str, Any],
    entity_type: str,
    profile: str,
    version: str,
    path_prefix: str = "",
) -> tuple[list[ValidationError], list[ValidationRule]]:
    """Recursively validate an entity and all nested entities.

    Args:
        values: Entity data to validate.
        entity_type: Entity type name.
        profile: Profile name.
        version: Profile version.
        path_prefix: Path prefix for nested errors (e.g., "samples[0].").

    Returns:
        Tuple of (error_list, rules_list).
    """
    error_list: list[ValidationError] = []
    rules = _get_validation_rules_for_entity(entity_type, profile, version)
    loader = SpecLoader(profile=profile)

    try:
        entity_spec = loader.load_entity(entity_type, version)
        model_class = create_model_from_spec(entity_spec)

        # Separate simple and nested fields
        simple_values, nested_fields = _separate_field_values(entity_spec, values)

        # Validate simple fields with Pydantic
        _validate_with_pydantic(model_class, simple_values, path_prefix, error_list)

        # Run custom validation rules
        _validate_with_custom_rules(values, entity_type, version, profile, path_prefix, error_list)

        # Recursively validate nested entities
        _validate_nested_entities(nested_fields, profile, version, path_prefix, error_list, rules)

    except FileNotFoundError:
        error_list.append(
            ValidationError(
                field=path_prefix.rstrip(".") or entity_type,
                message=f"Unknown entity type: {entity_type}",
                rule="error",
            )
        )
    except Exception as e:
        logger.warning("Validation error for %s: %s", entity_type, e, exc_info=True)
        error_list.append(
            ValidationError(
                field=path_prefix.rstrip(".") or entity_type,
                message=str(e),
                rule="error",
            )
        )

    return error_list, rules


def _separate_field_values(
    entity_spec, values: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, tuple[str, Any]]]:
    """Separate simple field values from nested entity values.

    Args:
        entity_spec: The entity specification.
        values: All field values.

    Returns:
        Tuple of (simple_values, nested_fields) where nested_fields maps
        field_name to (nested_type, nested_items).
    """
    simple_values = {}
    nested_fields = {}
    for field in entity_spec.fields:
        if field.name in values:
            if field.is_nested():
                nested_fields[field.name] = (field.items, values[field.name])
            else:
                simple_values[field.name] = values[field.name]
    return simple_values, nested_fields


def _validate_with_pydantic(
    model_class,
    values: dict[str, Any],
    path_prefix: str,
    error_list: list[ValidationError],
) -> None:
    """Validate values using Pydantic model.

    Args:
        model_class: The Pydantic model class.
        values: Values to validate.
        path_prefix: Path prefix for error fields.
        error_list: List to append errors to.
    """
    try:
        model_class(**values)
    except PydanticValidationError as e:
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            error_list.append(
                ValidationError(
                    field=f"{path_prefix}{field}",
                    message=err["msg"],
                    rule="constraint",
                )
            )


def _validate_with_custom_rules(
    values: dict[str, Any],
    entity_type: str,
    version: str,
    profile: str,
    path_prefix: str,
    error_list: list[ValidationError],
) -> None:
    """Run custom validation rules on entity values.

    Args:
        values: Values to validate.
        entity_type: Entity type name.
        version: Profile version.
        profile: Profile name.
        path_prefix: Path prefix for error fields.
        error_list: List to append errors to.
    """
    errors = validate_data(values, entity_type, version=version, profile=profile)
    for e in errors:
        error_list.append(
            ValidationError(
                field=f"{path_prefix}{e.field}",
                message=e.message,
                rule=e.rule,
            )
        )


def _validate_nested_entities(
    nested_fields: dict[str, tuple[str, Any]],
    profile: str,
    version: str,
    path_prefix: str,
    error_list: list[ValidationError],
    rules: list[ValidationRule],
) -> None:
    """Recursively validate nested entity fields.

    Args:
        nested_fields: Map of field_name to (nested_type, nested_items).
        profile: Profile name.
        version: Profile version.
        path_prefix: Path prefix for error fields.
        error_list: List to append errors to.
        rules: List to append rules to.
    """
    for field_name, (nested_type, nested_items) in nested_fields.items():
        if not nested_items or not nested_type:
            continue

        items_list = nested_items if isinstance(nested_items, list) else [nested_items]
        for idx, item in enumerate(items_list):
            if not isinstance(item, dict):
                continue
            nested_path = f"{path_prefix}{field_name}[{idx}]."
            nested_errors, nested_rules = _validate_entity_deep(
                item, nested_type, profile, version, nested_path
            )
            error_list.extend(nested_errors)
            # Add rules from nested entities (avoid duplicates)
            for rule in nested_rules:
                if rule not in rules:
                    rules.append(rule)


def register_validation_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    get_state: Callable[[], AppState],
) -> None:
    """Register validation routes on the FastAPI app.

    Args:
        app: FastAPI application instance.
        templates: Jinja2Templates instance.
        get_state: Callable returning AppState.
    """

    @app.post("/validate", response_class=HTMLResponse)
    async def validate_form(request: Request) -> HTMLResponse:
        """Validate form data against profile spec including all nested entities."""
        state = get_state()
        form_data = await request.form()
        entity_type = form_data.get("_entity_type")

        if not entity_type:
            return templates.TemplateResponse(
                request,
                "components/validation_result.html",
                {
                    "valid": False,
                    "errors": [
                        ValidationError(
                            field="_entity_type",
                            message="Entity type is required",
                            rule="required",
                        )
                    ],
                    "rules": [],
                },
            )

        facade = ProfileFacade(profile=state.profile)
        helper = getattr(facade, entity_type)
        values = collect_form_values(dict(form_data), helper)

        # Add nested items from state
        for field_name, items in state.current_nested_items.items():
            if items:
                values[field_name] = items

        # Perform deep validation of entity and all nested entities
        error_list, rules = _validate_entity_deep(
            values, entity_type, state.profile, facade.version
        )

        return templates.TemplateResponse(
            request,
            "components/validation_result.html",
            {"valid": len(error_list) == 0, "errors": error_list, "rules": rules},
        )
