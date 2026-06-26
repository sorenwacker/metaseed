"""Form helper functions for UI routes.

Contains FormContext class and utility functions for form handling,
field data collection, and validation error formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from metaseed.specs.schema import PRIMITIVE_TYPES


@dataclass
class FormContext:
    """Context for rendering entity forms.

    Encapsulates the common data needed to render entity forms,
    reducing parameter counts in rendering functions.
    """

    entity_type: str
    helper: Any
    values: dict[str, Any]
    node_id: str | None = None
    auto_fields: set[str] = field(default_factory=set)
    inline_tables: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def is_edit(self) -> bool:
        """Whether this is an edit form (vs create)."""
        return self.node_id is not None

    @property
    def description(self) -> str:
        """Entity description from helper."""
        return self.helper.description if self.helper else ""

    @property
    def ontology_term(self) -> str:
        """Ontology term from helper."""
        return self.helper.ontology_term if self.helper else ""

    def get_fields(self) -> list[dict[str, Any]]:
        """Get all field data for this entity."""
        return get_field_data(self.helper) if self.helper else []

    def get_required_fields(self) -> list[dict[str, Any]]:
        """Get required fields only."""
        return filter_fields(self.get_fields(), required=True)

    def get_optional_fields(self) -> list[dict[str, Any]]:
        """Get optional non-nested fields."""
        return filter_fields(self.get_fields(), required=False, exclude_nested=True)

    def get_nested_fields(self) -> list[dict[str, Any]]:
        """Get nested entity fields only."""
        return filter_fields(self.get_fields(), nested_only=True)


def filter_fields(
    fields: list[dict[str, Any]],
    *,
    required: bool | None = None,
    exclude_nested: bool = False,
    nested_only: bool = False,
) -> list[dict[str, Any]]:
    """Filter field list by criteria.

    Args:
        fields: List of field dicts from get_field_data().
        required: If True, only required fields. If False, only optional.
        exclude_nested: If True, exclude nested entity fields.
        nested_only: If True, only include nested entity fields.

    Returns:
        Filtered list of fields.
    """
    result = fields
    if required is not None:
        result = [f for f in result if f["required"] == required]
    if exclude_nested:
        result = [f for f in result if not is_nested_field(f)]
    if nested_only:
        result = [f for f in result if is_nested_field(f)]
    return result


def get_field_data(
    helper: Any, exclude_parent_ref: str | None = None
) -> list[dict[str, Any]]:
    """Get field data for template rendering.

    Args:
        helper: Entity helper with field info.
        exclude_parent_ref: If provided, exclude fields that reference this parent type.
                           Used when creating child entities to hide auto-filled parent refs.

    Returns:
        List of field dicts for template rendering.
    """
    fields = []
    for field_name in helper.all_fields:
        info = helper.field_info(field_name)

        # Check if this field references the parent type - if so, skip it
        if exclude_parent_ref:
            items = info.get("items")
            if items and items == exclude_parent_ref:
                continue
            # Also check field name patterns like "study_id" for parent "Study"
            parent_lower = exclude_parent_ref.lower()
            if field_name.lower() in [
                f"{parent_lower}_id",
                f"{parent_lower}_identifier",
                f"{parent_lower}_unique_id",
            ]:
                continue

        fields.append(
            {
                "name": field_name,
                "type": info["type"],
                "required": info["required"],
                "description": info.get("description", ""),
                "items": info.get("items"),
                "ontologies": info.get("ontologies"),
            }
        )
    return fields


def is_nested_field(field: dict[str, Any]) -> bool:
    """Check if a field dict represents a nested entity (list of entities or single entity).

    This function operates on field dicts from get_field_data(). For FieldSpec
    objects, use the is_nested() method directly.

    Args:
        field: Field dict with 'type' and optionally 'items' keys.

    Returns:
        True if the field contains nested entities, False otherwise.
    """
    if field["type"] == "entity":
        return True
    if field["type"] == "list":
        items = field.get("items")
        if items and items not in PRIMITIVE_TYPES:
            return True
    return False


def collect_form_values(form_data: dict[str, Any], helper: Any) -> dict[str, Any]:
    """Collect form values into a dictionary."""
    values: dict[str, Any] = {}
    for field_name in helper.all_fields:
        value = form_data.get(field_name)
        if value is None or value == "":
            continue

        info = helper.field_info(field_name)
        field_type = info["type"]

        if field_type == "integer":
            try:
                value = int(value)
            except ValueError:
                continue
        elif field_type == "float":
            try:
                value = float(value)
            except ValueError:
                continue
        elif field_type == "boolean":
            value = value.lower() in ("true", "1", "yes", "on")
        elif field_type == "list" and info.get("items") == "string":
            value = [line.strip() for line in str(value).split("\n") if line.strip()]

        values[field_name] = value

    return values


def format_validation_errors(e: ValidationError) -> str:
    """Format validation errors for display with user-friendly messages."""
    friendly_messages = []
    for err in e.errors():
        field = ".".join(str(loc) for loc in err["loc"])
        msg = err["msg"]

        # Make common error messages more user-friendly
        if "pattern" in msg.lower() and "email" in field.lower():
            msg = "Invalid email format"
        elif "pattern" in msg.lower() and (
            "date" in field.lower() or "date" in msg.lower()
        ):
            msg = "Invalid date format (use YYYY-MM-DD)"
        elif "pattern" in msg.lower() and "orcid" in field.lower():
            msg = "Invalid ORCID format (use XXXX-XXXX-XXXX-XXXX)"
        elif "pattern" in msg.lower():
            msg = "Invalid format"
        elif "required" in msg.lower():
            msg = "This field is required"

        friendly_messages.append(f"{field}: {msg}")

    return "; ".join(friendly_messages)


__all__ = [
    "FormContext",
    "collect_form_values",
    "filter_fields",
    "format_validation_errors",
    "get_field_data",
    "is_nested_field",
]
