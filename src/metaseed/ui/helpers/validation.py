"""Validation helpers for entity update operations.

Contains the ValidationResult dataclass and helper functions for processing
reference-linked children during entity updates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade

    from ..state import AppState

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Tracks validation errors and failed items during entity updates.

    Used to collect validation errors from child entity processing and
    preserve failed items so users can fix them.

    Attributes:
        errors: List of human-readable error messages.
        failed_items: Dict mapping field names to lists of items that failed validation.
    """

    errors: list[str] = field(default_factory=list)
    failed_items: dict[str, list[dict]] = field(default_factory=dict)

    def add_error(self, entity_type: str, message: str) -> None:
        """Add a validation error message.

        Args:
            entity_type: The entity type that had the error.
            message: Human-readable error message.
        """
        self.errors.append(f"{entity_type}: {message}")

    def add_failed_item(self, field_name: str, item: dict) -> None:
        """Add a failed item to be preserved for user correction.

        Args:
            field_name: The field name (e.g., "files") containing the item.
            item: The item dict that failed validation.
        """
        if field_name not in self.failed_items:
            self.failed_items[field_name] = []
        self.failed_items[field_name].append(item)

    def has_errors(self) -> bool:
        """Check if any validation errors occurred.

        Returns:
            True if there are validation errors, False otherwise.
        """
        return len(self.errors) > 0


def _format_validation_error(_entity_type: str, error: ValidationError) -> str:
    """Format a Pydantic ValidationError into a human-readable message.

    Args:
        _entity_type: The entity type that had the error (reserved for future use).
        error: The Pydantic ValidationError.

    Returns:
        Human-readable error message.
    """
    err = error.errors()[0] if error.errors() else {}
    err_type = err.get("type", "")

    if err_type == "missing":
        missing = [str(e["loc"][0]) for e in error.errors() if e["type"] == "missing"]
        return f"Missing required: {', '.join(missing)}"
    if err_type == "extra_forbidden":
        extra = [str(e["loc"][0]) for e in error.errors() if e["type"] == "extra_forbidden"]
        return f"Unknown fields: {', '.join(extra)}"
    return err.get("msg", str(error))


def _find_existing_child_node(
    state: AppState,
    child_type: str,
    item_id: str | None,
) -> Any | None:
    """Find an existing node for a child item.

    Args:
        state: Application state containing nodes.
        child_type: The child entity type.
        item_id: The item's node_id, alias, or unique_id.

    Returns:
        The existing TreeNode if found, None otherwise.
    """
    if not item_id:
        return None

    existing_node = state.nodes_by_id.get(item_id)
    if existing_node:
        return existing_node

    # Try to find by identifier
    for node in state.nodes_by_id.values():
        if node.entity_type == child_type:
            node_data = node.instance.model_dump() if node.instance else {}
            if node_data.get("alias") == item_id or node_data.get("unique_id") == item_id:
                return node

    return None


def _clean_item_for_child_entity(
    item: dict,
    child_helper: Any,
    parent_ref_field: str | None,
    parent_identifier: str | None,
) -> dict:
    """Clean and prepare an item dict for creating/updating a child entity.

    Args:
        item: The raw item dict from the form.
        child_helper: The child entity's helper.
        parent_ref_field: Field name that references the parent.
        parent_identifier: Parent's identifier value.

    Returns:
        Cleaned dict with only valid fields and parent reference set.
    """
    valid_fields = set(child_helper.all_fields)
    cleaned = {k: v for k, v in item.items() if not k.startswith("_") and v and k in valid_fields}

    if parent_ref_field and parent_identifier:
        cleaned[parent_ref_field] = parent_identifier

    return cleaned


def process_reference_linked_children(
    state: AppState,
    facade: ProfileFacade,
    node_id: str,
    helper: Any,
    entity_type: str,
    parent_identifier: str | None,
) -> ValidationResult:
    """Process reference-linked children (entities added via reference fields).

    These are NOT in helper.nested_fields but ARE in current_nested_items.
    Examples: files added to Run via run_ref field.

    Args:
        state: Application state containing nodes and nested items.
        facade: Profile facade for entity helpers.
        node_id: ID of the parent node being updated.
        helper: Parent entity's helper.
        entity_type: Parent entity type (e.g., "Run").
        parent_identifier: Parent's alias or unique_id.

    Returns:
        ValidationResult with any errors and failed items.
    """
    from .table_helpers import infer_entity_type_from_field

    result = ValidationResult()

    for field_name, items in state.current_nested_items.items():
        if field_name in helper.nested_fields:
            continue  # Skip spec-defined nested fields (handled elsewhere)

        child_type = infer_entity_type_from_field(facade, entity_type, field_name)
        if not child_type:
            continue

        child_helper = getattr(facade, child_type, None)
        if not child_helper:
            continue

        # Find the reference field that points back to parent
        parent_ref_field = None
        for ref_field, (target_type, _) in child_helper.reference_fields.items():
            if target_type == entity_type:
                parent_ref_field = ref_field
                break

        _process_child_items(
            state=state,
            items=items,
            child_type=child_type,
            child_helper=child_helper,
            parent_ref_field=parent_ref_field,
            parent_identifier=parent_identifier,
            node_id=node_id,
            field_name=field_name,
            result=result,
        )

    return result


def _process_child_items(
    state: AppState,
    items: list,
    child_type: str,
    child_helper: Any,
    parent_ref_field: str | None,
    parent_identifier: str | None,
    node_id: str,
    field_name: str,
    result: ValidationResult,
) -> None:
    """Process a list of child items, creating or updating nodes.

    Args:
        state: Application state.
        items: List of item dicts to process.
        child_type: Child entity type.
        child_helper: Child entity's helper.
        parent_ref_field: Field referencing parent.
        parent_identifier: Parent's identifier.
        node_id: Parent node ID.
        field_name: Field name for error tracking.
        result: ValidationResult to update.
    """
    for item in items:
        if not isinstance(item, dict):
            continue

        logger.info(f"Processing {child_type} item: {list(item.keys())}")

        item_id = item.get("_node_id") or item.get("alias") or item.get("unique_id")
        existing_node = _find_existing_child_node(state, child_type, item_id)

        cleaned = _clean_item_for_child_entity(
            item, child_helper, parent_ref_field, parent_identifier
        )
        if not cleaned:
            continue

        if existing_node:
            _update_existing_child(
                state, existing_node, child_type, child_helper, cleaned, field_name, item, result
            )
        else:
            _create_new_child(
                state, child_type, child_helper, cleaned, node_id, field_name, item, result
            )


def _update_existing_child(
    state: AppState,
    existing_node: Any,
    child_type: str,
    child_helper: Any,
    cleaned: dict,
    field_name: str,
    item: dict,
    result: ValidationResult,
) -> None:
    """Update an existing child node.

    Args:
        state: Application state.
        existing_node: The existing TreeNode.
        child_type: Child entity type.
        child_helper: Child entity's helper.
        cleaned: Cleaned item data.
        field_name: Field name for error tracking.
        item: Original item dict.
        result: ValidationResult to update.
    """
    try:
        child_instance = child_helper.create(**cleaned)
        state.update_node(existing_node.id, child_instance)
    except ValidationError as e:
        logger.warning(f"Validation error updating {child_type}: {e}")
        result.add_error(child_type, _format_validation_error(child_type, e))
        result.add_failed_item(field_name, item)
    except Exception as e:
        logger.warning(f"Error updating {child_type}: {e}")


def _create_new_child(
    state: AppState,
    child_type: str,
    child_helper: Any,
    cleaned: dict,
    node_id: str,
    field_name: str,
    item: dict,
    result: ValidationResult,
) -> None:
    """Create a new child node.

    Args:
        state: Application state.
        child_type: Child entity type.
        child_helper: Child entity's helper.
        cleaned: Cleaned item data.
        node_id: Parent node ID.
        field_name: Field name for error tracking.
        item: Original item dict.
        result: ValidationResult to update.
    """
    try:
        logger.info(f"Creating {child_type} with data: {cleaned}")
        child_instance = child_helper.create(**cleaned)
        state.add_node(child_type, child_instance, parent_id=node_id)
    except ValidationError as e:
        logger.warning(f"Validation error creating {child_type} with {cleaned}: {e}")
        result.add_error(child_type, _format_validation_error(child_type, e))
        result.add_failed_item(field_name, item)
    except Exception as e:
        logger.warning(f"Error creating {child_type}: {e}")


def rebuild_nested_items_with_failures(
    state: AppState,
    node_id: str,
    helper: Any,
    facade: ProfileFacade,
    failed_items: dict[str, list[dict]],
) -> None:
    """Rebuild nested items after update, including failed items for correction.

    Args:
        state: Application state.
        node_id: ID of the updated node.
        helper: Entity helper.
        facade: Profile facade.
        failed_items: Dict of field_name -> list of failed items to preserve.
    """
    from .entity_helpers import extract_nested_items, get_nested_items_for_edit

    updated_node = state.nodes_by_id.get(node_id)
    if updated_node:
        state.current_nested_items = get_nested_items_for_edit(updated_node, helper, facade)
    else:
        # Fallback - shouldn't happen but handle gracefully
        instance = state.nodes_by_id.get(node_id)
        if instance:
            state.current_nested_items = extract_nested_items(instance, helper)
        else:
            state.current_nested_items = {}

    # Add back any items that failed validation so user can fix them
    for field_name, items in failed_items.items():
        if field_name not in state.current_nested_items:
            state.current_nested_items[field_name] = []
        for item in items:
            # Mark as having validation error
            item["_validation_error"] = True
            state.current_nested_items[field_name].append(item)


__all__ = [
    "ValidationResult",
    "process_reference_linked_children",
    "rebuild_nested_items_with_failures",
]
