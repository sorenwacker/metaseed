"""Entity management tools for MCP server.

Uses EntityService for all CRUD operations to avoid code duplication.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from metaseed.utils.json import DateAwareEncoder

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _auto_save_dataset() -> None:
    """Auto-save the current dataset after entity operations."""
    from metaseed.agent.mcp.server import get_mcp_state
    from metaseed.logging import get_logger
    from metaseed.ui.datasets import auto_save

    logger = get_logger(__name__)

    try:
        state = get_mcp_state()
        auto_save(state)
    except Exception as e:
        logger.debug(f"MCP auto-save skipped: {e}")


def _get_current_dataset_info() -> dict[str, Any]:
    """Get info about the current dataset for safety checks."""
    from metaseed.agent.mcp.server import get_mcp_state
    from metaseed.ui.datasets import get_current_dataset_name

    try:
        state = get_mcp_state()
        return {
            "dataset": get_current_dataset_name(state),
            "profile": state.profile,
            "version": state.version,
        }
    except Exception:
        return {"dataset": None, "profile": None, "version": None}


def _check_dataset(expected_dataset: str | None) -> str | None:
    """Check if expected dataset matches current. Returns error message if mismatch."""
    if expected_dataset is None:
        return None

    info = _get_current_dataset_info()
    current = info.get("dataset")

    if current != expected_dataset:
        return f"Dataset mismatch: expected '{expected_dataset}' but current is '{current}'"
    return None


def _get_entity_field_info(entity_type: str) -> dict[str, Any] | None:
    """Get field info for an entity type from the current facade.

    Returns dict with valid_fields and required_fields, or None if entity not found.
    """
    from metaseed.agent.mcp.server import get_mcp_state

    try:
        state = get_mcp_state()
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return None

        valid_fields = [f.name for f in helper._spec.fields]
        required_fields = [f.name for f in helper._spec.fields if f.required]

        return {
            "valid_fields": valid_fields,
            "required_fields": required_fields,
        }
    except Exception:
        return None


def _auto_fill_reference_fields(
    entity_type: str,
    entity_data: dict[str, Any],
    service: Any,
) -> dict[str, Any]:
    """Auto-fill missing reference fields when there's exactly one candidate parent.

    For example, if creating a Sample without study_ref, and there's exactly one
    Study in the dataset, automatically set study_ref to that Study's alias.

    Args:
        entity_type: Type of entity being created.
        entity_data: The entity data dict (will be modified in place).
        service: EntityService instance.

    Returns:
        The modified entity_data dict.
    """
    import logging

    logger = logging.getLogger(__name__)
    from metaseed.agent.mcp.server import get_mcp_state

    try:
        state = get_mcp_state()
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return entity_data

        # Check each reference field
        for field in helper._spec.fields:
            if not field.reference:
                continue

            # Skip if already set
            if entity_data.get(field.name):
                continue

            # Parse reference format: "EntityType.field"
            parts = field.reference.split(".", 1)
            if len(parts) != 2:
                continue

            target_entity_type, target_field = parts

            # Get all entities of target type
            all_entities = service.list_entities(target_entity_type)
            entities_list = all_entities.get("entities", {}).get(target_entity_type, [])

            logger.info(
                f"Auto-fill check: {entity_type}.{field.name} -> {target_entity_type}, "
                f"found {len(entities_list)} candidates"
            )

            # Auto-fill only if exactly one candidate exists
            if len(entities_list) == 1:
                parent_data = entities_list[0].get("data", {})
                ref_value = parent_data.get(target_field)
                if ref_value:
                    entity_data[field.name] = ref_value
                    logger.info(f"Auto-filled {field.name}={ref_value}")

    except Exception as e:
        logger.warning(f"Auto-fill failed: {e}")

    return entity_data


def _find_parent_from_references(
    entity_type: str,
    entity_data: dict[str, Any],
    service: Any,
) -> tuple[str | None, str | None]:
    """Auto-detect parent entity from reference fields in the data.

    Looks for fields like study_ref, sample_ref, experiment_ref that reference
    other entities, and finds the matching parent entity.

    Args:
        entity_type: Type of entity being created.
        entity_data: The entity data dict.
        service: EntityService instance.

    Returns:
        Tuple of (parent_node_id, parent_field_name) or (None, None) if not found.
    """
    from metaseed.agent.mcp.server import get_mcp_state

    try:
        state = get_mcp_state()
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return None, None

        # Check each field for references
        for field in helper._spec.fields:
            if not field.reference:
                continue

            # Parse reference format: "EntityType.field"
            parts = field.reference.split(".", 1)
            if len(parts) != 2:
                continue

            target_entity_type, target_field = parts

            # Get the reference value from entity data
            ref_value = entity_data.get(field.name)
            if not ref_value:
                continue

            # Find the parent entity by searching all entities of target type
            all_entities = service.list_entities(target_entity_type)
            entities_list = all_entities.get("entities", {}).get(target_entity_type, [])

            for entity in entities_list:
                entity_id = entity.get("id")
                data = entity.get("data", {})
                # Check if this entity's target field matches the reference value
                if data.get(target_field) == ref_value:
                    # Found the parent! Also find which field on parent holds children of this type
                    parent_helper = getattr(facade, target_entity_type, None)
                    parent_field = None
                    if parent_helper:
                        for fname, ftype in parent_helper.nested_fields.items():
                            if ftype == entity_type:
                                parent_field = fname
                                break
                    return entity_id, parent_field

    except Exception:  # noqa: S110
        # Silently return None on any error - parent detection is optional
        pass

    return None, None


def _format_validation_error(
    error: ValidationError,
    entity_type: str,
) -> dict[str, Any]:
    """Format a Pydantic ValidationError into a helpful response.

    Args:
        error: The Pydantic ValidationError.
        entity_type: Entity type for field lookup.

    Returns:
        Dict with error details, valid_fields, and required_fields.
    """
    details = []
    for err in error.errors():
        field = ".".join(str(loc) for loc in err["loc"])
        details.append(
            {
                "field": field,
                "message": err["msg"],
                "type": err["type"],
            }
        )

    result: dict[str, Any] = {
        "error": "Validation failed",
        "details": details,
    }

    # Add field hints
    field_info = _get_entity_field_info(entity_type)
    if field_info:
        result["valid_fields"] = field_info["valid_fields"]
        result["required_fields"] = field_info["required_fields"]

    return result


def _handle_validation_error(
    error: Exception, entity_type: str
) -> dict[str, Any] | None:
    """Check if exception is or wraps a ValidationError and format it.

    Args:
        error: Exception to check.
        entity_type: Entity type for field hints.

    Returns:
        Formatted error dict if ValidationError, None otherwise.
    """
    if isinstance(error, ValidationError):
        return _format_validation_error(error, entity_type)
    if hasattr(error, "__cause__") and isinstance(error.__cause__, ValidationError):
        return _format_validation_error(error.__cause__, entity_type)
    return None


def register_entity_tools(mcp: FastMCP, get_entity_service) -> None:
    """Register entity management tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        get_entity_service: Function to get EntityService instance.
    """

    @mcp.tool()
    def list_entities(entity_type: str | None = None) -> str:
        """List all entities in the current dataset.

        Returns entities with their data, organized by type.

        Args:
            entity_type: Optional filter by entity type (e.g., "Investigation").

        Returns:
            JSON with entities by type, each with index and data.
        """
        try:
            service = get_entity_service()
            result = service.list_entities(entity_type)
            return json.dumps(result, indent=2, cls=DateAwareEncoder)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_entity_tree() -> str:
        """Get the hierarchical entity tree structure.

        Shows parent-child relationships between entities.
        Useful for understanding how entities are connected.

        Returns:
            JSON with nested tree structure showing entity hierarchy.
        """
        try:
            service = get_entity_service()
            result = service.get_tree()
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_entity(node_id: str) -> str:
        """Get a specific entity by its node ID.

        Args:
            node_id: The entity's node ID from list_entities.

        Returns:
            JSON with entity type, label, and full data.
        """
        try:
            service = get_entity_service()
            result = service.get_entity(node_id)
            if result is None:
                return json.dumps({"error": f"Entity not found: {node_id}"})
            return json.dumps(result, indent=2, cls=DateAwareEncoder)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def create_entity(
        entity_type: str,
        data: str,
        parent_id: str | None = None,
        expected_dataset: str | None = None,
    ) -> str:
        """Create a new entity in the current dataset.

        IMPORTANT: Only include data explicitly stated in source files.
        Do not assume, infer, or generate placeholder values.

        Parent relationships are validated against the schema:
        - PhenotypingSample must be under ObservationUnit, not Study
        - BiologicalMaterial must be under Study, not Investigation
        - Invalid parent types will return an error

        Auto-saves the dataset after creation.

        Args:
            entity_type: Entity type (e.g., "Investigation", "Study", "Sample").
            data: JSON string of field values from source (no assumptions).
            parent_id: Parent entity ID. Must be a valid parent type per schema.
                      If not provided, auto-detects from reference fields.
            expected_dataset: Optional safety check - if provided, operation fails
                             if current dataset name doesn't match.

        Returns:
            JSON with created entity info including parent relationship.
            On error, returns details about invalid parent type or validation failures.
        """
        # Safety check: verify we're editing the expected dataset
        if expected_dataset:
            mismatch_error = _check_dataset(expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            entity_data = json.loads(data)

            # Auto-fill missing reference fields (e.g., study_ref) when unambiguous
            entity_data = _auto_fill_reference_fields(entity_type, entity_data, service)

            # Auto-detect parent from reference fields if not explicitly provided
            if not parent_id:
                auto_detected_parent, _ = _find_parent_from_references(
                    entity_type, entity_data, service
                )
                if auto_detected_parent:
                    parent_id = auto_detected_parent

            # Service.create_entity handles adding to parent's nested array
            result = service.create_entity(entity_type, entity_data, parent_id)

            # Add dataset info to response
            result["_dataset"] = _get_current_dataset_info()

            # Add linked_via_field info if parent was specified
            if parent_id:
                parent = service.get_entity(parent_id)
                if parent:
                    # Find which field on parent references this entity type
                    from metaseed.agent.mcp.server import get_mcp_state

                    state = get_mcp_state()
                    facade = state.get_or_create_facade()
                    parent_helper = getattr(facade, parent["entity_type"], None)
                    if parent_helper:
                        for field_name, ref_type in parent_helper.nested_fields.items():
                            if ref_type == entity_type:
                                result["linked_via_field"] = field_name
                                break

            # Auto-save to persist changes
            _auto_save_dataset()

            return json.dumps(result, indent=2)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            validation_error = _handle_validation_error(e, entity_type)
            if validation_error:
                return json.dumps(validation_error, indent=2)
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def update_entity(
        node_id: str,
        data: str,
        expected_dataset: str | None = None,
    ) -> str:
        """Update an existing entity.

        Merges the provided data with the existing entity.
        Auto-saves the dataset after update.

        Args:
            node_id: The entity's node ID.
            data: JSON string of fields to update.
            expected_dataset: Optional safety check - if provided, operation fails
                             if current dataset name doesn't match.

        Returns:
            JSON with updated entity info and dataset name, or error.
        """
        # Safety check
        if expected_dataset:
            mismatch_error = _check_dataset(expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            updates = json.loads(data)
            result = service.update_entity(node_id, updates)
            result["_dataset"] = _get_current_dataset_info()

            # Auto-save to persist changes
            _auto_save_dataset()

            return json.dumps(result, indent=2)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def delete_entity(node_id: str, expected_dataset: str | None = None) -> str:
        """Delete an entity from the current dataset.

        Removes the entity and auto-saves the dataset.

        Args:
            node_id: The entity's node ID.
            expected_dataset: Optional safety check - if provided, operation fails
                             if current dataset name doesn't match.

        Returns:
            JSON with deletion status and dataset name.
        """
        # Safety check
        if expected_dataset:
            mismatch_error = _check_dataset(expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            result = service.delete_entity(node_id)
            result["_dataset"] = _get_current_dataset_info()

            # Auto-save to persist changes
            _auto_save_dataset()

            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def bulk_update_entities(updates: str, expected_dataset: str | None = None) -> str:
        """Update multiple entities at once.

        Applies updates to multiple entities in a single operation.
        Auto-saves after all updates are applied.

        Args:
            updates: JSON array of updates, each with "id" and "data" fields.
                    Example: [{"id": "abc123", "data": {"title": "New Title"}}]
            expected_dataset: Optional safety check - if provided, operation fails
                             if current dataset name doesn't match.

        Returns:
            JSON with results for each update and dataset name.
        """
        # Safety check
        if expected_dataset:
            mismatch_error = _check_dataset(expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            update_list = json.loads(updates)

            if not isinstance(update_list, list):
                return json.dumps({"error": "Updates must be a JSON array"})

            results = []
            for item in update_list:
                node_id = item.get("id")
                data = item.get("data", {})

                try:
                    result = service.update_entity(node_id, data)
                    results.append(
                        {
                            "id": node_id,
                            "status": "updated",
                            "label": result.get("label"),
                        }
                    )
                except ValueError as e:
                    results.append(
                        {
                            "id": node_id,
                            "status": "error",
                            "message": str(e),
                        }
                    )

            # Auto-save to persist changes
            _auto_save_dataset()

            return json.dumps(
                {
                    "total": len(update_list),
                    "updated": sum(1 for r in results if r["status"] == "updated"),
                    "errors": sum(1 for r in results if r["status"] == "error"),
                    "results": results,
                    "_dataset": _get_current_dataset_info(),
                },
                indent=2,
            )
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def batch_create(entities: str, expected_dataset: str | None = None) -> str:
        """Create multiple entities in a single operation.

        IMPORTANT: Only create entities with data explicitly stated in source files.
        Do not assume, infer, or generate placeholder data.

        Creates entities in order. Use parent_id to establish hierarchies.
        Parent-child relationships are validated against the schema.
        Results include both successes and failures with detailed error info.

        Args:
            entities: JSON array of entity specs, each with:
                - entity_type: Entity type (e.g., "Investigation", "Study")
                - data: Field values explicitly from source (no assumptions)
                - parent_id: Parent entity ID (must be valid parent type)
            expected_dataset: Optional safety check - if provided, operation fails
                             if current dataset name doesn't match.

        Returns:
            JSON with total, created, failed counts, dataset info, and per-entity results.
            Failed entities include error messages about invalid parent types.
        """
        # Safety check: verify we're editing the expected dataset
        if expected_dataset:
            mismatch_error = _check_dataset(expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            entity_list = json.loads(entities)

            if not isinstance(entity_list, list):
                return json.dumps({"error": "Input must be a JSON array"})

            results = []
            for idx, spec in enumerate(entity_list):
                entity_type = spec.get("entity_type")
                data = spec.get("data", {})
                parent_id = spec.get("parent_id")

                if not entity_type:
                    results.append(
                        {
                            "index": idx,
                            "status": "error",
                            "message": "Missing entity_type",
                        }
                    )
                    continue

                try:
                    result = service.create_entity(entity_type, data, parent_id)
                    results.append(
                        {
                            "index": idx,
                            "status": "created",
                            "id": result["id"],
                            "entity_type": entity_type,
                            "label": result.get("label"),
                        }
                    )
                except Exception as e:
                    validation_error = _handle_validation_error(e, entity_type)
                    if validation_error:
                        results.append(
                            {
                                "index": idx,
                                "status": "error",
                                "entity_type": entity_type,
                                "message": "Validation failed",
                                "details": validation_error.get("details", []),
                            }
                        )
                    else:
                        results.append(
                            {
                                "index": idx,
                                "status": "error",
                                "entity_type": entity_type,
                                "message": str(e),
                            }
                        )

            # Auto-save to persist changes
            _auto_save_dataset()

            return json.dumps(
                {
                    "total": len(entity_list),
                    "created": sum(1 for r in results if r["status"] == "created"),
                    "failed": sum(1 for r in results if r["status"] == "error"),
                    "results": results,
                    "_dataset": _get_current_dataset_info(),
                },
                indent=2,
            )
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
