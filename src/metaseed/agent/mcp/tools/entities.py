"""Entity management tools for MCP server.

Uses EntityService for all CRUD operations to avoid code duplication.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from metaseed.agent.mcp.ui_session import ui_datasets
from metaseed.facade.linking import target_reference_field
from metaseed.utils.json import DateAwareEncoder

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from metaseed.agent.mcp.context import MCPContext, ResolveContext
    from metaseed.agent.mcp.ui_session import AppState, EntityService


def _auto_save_dataset(ctx: MCPContext) -> None:
    """Auto-save the dataset of the session this call is serving.

    Takes the whole context, not just the state: the write must go through the
    session's own factory, or a host serving two callers would read from one
    repository and write to another.
    """
    from metaseed.logging import get_logger

    logger = get_logger(__name__)

    try:
        ui_datasets.auto_save(ctx.state, factory=ctx.dataset_factory)
    except Exception as e:
        logger.debug(f"MCP auto-save skipped: {e}")


def _get_current_dataset_info(state: AppState) -> dict[str, Any]:
    """Get info about the current dataset for safety checks."""
    try:
        return {
            "dataset": ui_datasets.get_current_dataset_name(state),
            "profile": state.profile,
            "version": state.version,
        }
    except Exception:
        return {"dataset": None, "profile": None, "version": None}


def _check_dataset(state: AppState, expected_dataset: str | None) -> str | None:
    """Check if expected dataset matches current. Returns error message if mismatch."""
    if expected_dataset is None:
        return None

    info = _get_current_dataset_info(state)
    current = info.get("dataset")

    if current != expected_dataset:
        return f"Dataset mismatch: expected '{expected_dataset}' but current is '{current}'"
    return None


def _get_entity_field_info(state: AppState, entity_type: str) -> dict[str, Any] | None:
    """Get field info for an entity type from the current facade.

    Returns dict with valid_fields, required_fields, the identifier_field, and a
    per-field type map, or None if the entity type is not found. The identifier
    is included so callers stop assuming a generic ``unique_id`` on entities
    (e.g. Person) that key on a different field.
    """
    try:
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return None

        valid_fields = [f.name for f in helper._spec.fields]
        required_fields = [f.name for f in helper._spec.fields if f.required]
        field_types = {
            f.name: (f.type.value if hasattr(f.type, "value") else str(f.type))
            for f in helper._spec.fields
        }

        return {
            "identifier_field": helper.identifier_field,
            "valid_fields": valid_fields,
            "required_fields": required_fields,
            "field_types": field_types,
        }
    except Exception:
        return None


def _creation_hints(state: AppState, entity_type: str) -> dict[str, Any] | None:
    """Build next-step hints for a freshly created entity.

    Surfaces the child types it can contain, a suggested next action, and which
    other entities' reference fields are expected to point back at it, so an
    agent keeps building the dataset relationally instead of stopping flat.

    Args:
        entity_type: The entity type just created.

    Returns:
        Hints dict, or None if no relationships apply or the type is unknown.
    """
    try:
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return None

        children = sorted(set(helper.nested_fields.values()))
        consumers = []
        for other in facade.entities:
            other_helper = getattr(facade, other, None)
            if not other_helper:
                continue
            for field, (
                target_type,
                _target_field,
            ) in other_helper.reference_fields.items():
                if target_type == entity_type:
                    consumers.append(f"{other}.{field}")

        hints: dict[str, Any] = {}
        if children:
            hints["expected_children"] = children
            hints["typical_next"] = (
                f"Create {children[0]} entities with parent_id set to this entity"
            )
        if consumers:
            hints["cross_ref_consumers"] = sorted(consumers)
        return hints or None
    except Exception:
        return None


def _field_constraint_detail(
    state: AppState, entity_type: str, field_name: str
) -> dict[str, Any] | None:
    """Return a field's description and constraints for error feedback.

    Surfaces the pattern, range, enum, etc. a value must satisfy so a format
    error explains the expected shape instead of only Pydantic's generic text.

    Args:
        entity_type: Entity type owning the field.
        field_name: Field that failed validation.

    Returns:
        Dict with optional ``description`` and ``constraints``, or None.
    """
    try:
        helper = getattr(state.get_or_create_facade(), entity_type, None)
        if not helper:
            return None
        info = helper.field_info(field_name)
    except Exception:
        return None

    out: dict[str, Any] = {}
    if info.get("description"):
        out["description"] = info["description"]
    if info.get("constraints"):
        out["constraints"] = info["constraints"]
    return out or None


def _auto_fill_reference_fields(
    state: AppState,
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
    try:
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return entity_data

        # Check each reference field, using the facade's parsed reference map
        # ({field_name: (target_entity, target_field)}) rather than re-parsing specs.
        for field_name, (
            target_entity_type,
            target_field,
        ) in helper.reference_fields.items():
            # Skip if already set
            if entity_data.get(field_name):
                continue

            # Get all entities of target type
            all_entities = service.list_entities(target_entity_type)
            entities_list = all_entities.get("entities", {}).get(target_entity_type, [])

            logger.info(
                f"Auto-fill check: {entity_type}.{field_name} -> {target_entity_type}, "
                f"found {len(entities_list)} candidates"
            )

            # Auto-fill only if exactly one candidate exists
            if len(entities_list) == 1:
                parent_data = entities_list[0].get("data", {})
                ref_value = parent_data.get(target_field)
                if ref_value:
                    entity_data[field_name] = ref_value
                    logger.info(f"Auto-filled {field_name}={ref_value}")

    except Exception as e:
        logger.warning(f"Auto-fill failed: {e}")

    return entity_data


def _find_parent_from_references(
    state: AppState,
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
    try:
        facade = state.get_or_create_facade()
        helper = getattr(facade, entity_type, None)
        if not helper:
            return None, None

        # Check each reference field, using the facade's parsed reference map
        # ({field_name: (target_entity, target_field)}) rather than re-parsing specs.
        for field_name, (
            target_entity_type,
            target_field,
        ) in helper.reference_fields.items():
            # Get the reference value from entity data
            ref_value = entity_data.get(field_name)
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
                    # ADR 005: linking.py owns which field references a child
                    # of a given type. Deriving it here was a second home.
                    parent_field = (
                        target_reference_field(parent_helper, entity_type)
                        if parent_helper
                        else None
                    )
                    return entity_id, parent_field

    except Exception:  # noqa: S110
        # Silently return None on any error - parent detection is optional
        pass

    return None, None


def _format_validation_error(
    state: AppState,
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
        loc = err["loc"]
        field = ".".join(str(part) for part in loc)
        detail: dict[str, Any] = {
            "field": field,
            "message": err["msg"],
            "type": err["type"],
        }
        # Attach the expected format (description, pattern, range, enum) so a
        # bad value is corrected against the spec, not just flagged.
        if loc:
            constraint = _field_constraint_detail(state, entity_type, str(loc[0]))
            if constraint:
                detail.update(constraint)
        details.append(detail)

    result: dict[str, Any] = {
        "error": "Validation failed",
        "details": details,
    }

    # Add field hints
    field_info = _get_entity_field_info(state, entity_type)
    if field_info:
        result["identifier_field"] = field_info["identifier_field"]
        result["valid_fields"] = field_info["valid_fields"]
        result["required_fields"] = field_info["required_fields"]
        result["field_types"] = field_info["field_types"]

        # Targeted hint for the common confusion: an id alias was sent to an
        # entity whose identifier is a different field (e.g. Person uses 'name').
        identifier = field_info["identifier_field"]
        id_aliases = {"unique_id", "id", "identifier"}
        rejected = {
            d["field"]
            for d in details
            if d.get("type") == "extra_forbidden" and d["field"] in id_aliases
        }
        if rejected and identifier and identifier not in id_aliases:
            sent = sorted(rejected)
            result["hint"] = (
                f"{entity_type} has no {', '.join(repr(f) for f in sent)} field; "
                f"its identifier is {identifier!r}. Remove "
                f"{', '.join(repr(f) for f in sent)} and use {identifier!r}."
            )

    return result


def _handle_validation_error(
    state: AppState, error: Exception, entity_type: str
) -> dict[str, Any] | None:
    """Check if exception is or wraps a ValidationError and format it.

    Args:
        error: Exception to check.
        entity_type: Entity type for field hints.

    Returns:
        Formatted error dict if ValidationError, None otherwise.
    """
    if isinstance(error, ValidationError):
        return _format_validation_error(state, error, entity_type)
    if hasattr(error, "__cause__") and isinstance(error.__cause__, ValidationError):
        return _format_validation_error(state, error.__cause__, entity_type)
    return None


def register_entity_tools(  # noqa: C901
    mcp: FastMCP, resolve_context: ResolveContext
) -> None:
    """Register entity management tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        resolve_context: Returns the context for the call being served. Called
            inside each tool body, which is the only scope where the caller is
            identifiable, so two callers on one process never share a session.
    """

    def current_state() -> AppState:
        """The state of the session this call is serving.

        Named to avoid colliding with the ``state`` locals several tools use.
        """
        return resolve_context().state

    def get_entity_service() -> EntityService:
        """The entity service of the session this call is serving."""
        return resolve_context().get_entity_service()

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
            mismatch_error = _check_dataset(current_state(), expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            entity_data = json.loads(data)

            # Auto-fill missing reference fields (e.g., study_ref) when unambiguous
            entity_data = _auto_fill_reference_fields(
                current_state(), entity_type, entity_data, service
            )

            # Auto-detect parent from reference fields if not explicitly provided
            if not parent_id:
                auto_detected_parent, _ = _find_parent_from_references(
                    current_state(), entity_type, entity_data, service
                )
                if auto_detected_parent:
                    parent_id = auto_detected_parent

            # Service.create_entity handles adding to parent's nested array
            result = service.create_entity(entity_type, entity_data, parent_id)

            # Add dataset info to response
            result["_dataset"] = _get_current_dataset_info(current_state())

            # Suggest how to keep building the dataset relationally
            hints = _creation_hints(current_state(), entity_type)
            if hints:
                result["hints"] = hints

            # Add linked_via_field info if parent was specified
            if parent_id:
                parent = service.get_entity(parent_id)
                if parent:
                    # Find which field on parent references this entity type
                    facade = current_state().get_or_create_facade()
                    parent_helper = getattr(facade, parent["entity_type"], None)
                    if parent_helper:
                        linked_via = target_reference_field(parent_helper, entity_type)
                        if linked_via is not None:
                            result["linked_via_field"] = linked_via

            # Auto-save to persist changes
            _auto_save_dataset(resolve_context())

            return json.dumps(result, indent=2)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            validation_error = _handle_validation_error(current_state(), e, entity_type)
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
            mismatch_error = _check_dataset(current_state(), expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            updates = json.loads(data)
            result = service.update_entity(node_id, updates)
            result["_dataset"] = _get_current_dataset_info(current_state())

            # Auto-save to persist changes
            _auto_save_dataset(resolve_context())

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
            mismatch_error = _check_dataset(current_state(), expected_dataset)
            if mismatch_error:
                return json.dumps({"error": mismatch_error})

        try:
            service = get_entity_service()
            result = service.delete_entity(node_id)
            result["_dataset"] = _get_current_dataset_info(current_state())

            # Auto-save to persist changes
            _auto_save_dataset(resolve_context())

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
            mismatch_error = _check_dataset(current_state(), expected_dataset)
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
            _auto_save_dataset(resolve_context())

            return json.dumps(
                {
                    "total": len(update_list),
                    "updated": sum(1 for r in results if r["status"] == "updated"),
                    "errors": sum(1 for r in results if r["status"] == "error"),
                    "results": results,
                    "_dataset": _get_current_dataset_info(current_state()),
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
            mismatch_error = _check_dataset(current_state(), expected_dataset)
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
                    # Match create_entity: fill a missing reference field when
                    # exactly one candidate parent exists, so batched entities
                    # are linked consistently with singly-created ones.
                    data = _auto_fill_reference_fields(
                        current_state(), entity_type, data, service
                    )
                    result = service.create_entity(entity_type, data, parent_id)
                    created = {
                        "index": idx,
                        "status": "created",
                        "id": result["id"],
                        "entity_type": entity_type,
                        "label": result.get("label"),
                    }
                    hints = _creation_hints(current_state(), entity_type)
                    if hints:
                        created["hints"] = hints
                    results.append(created)
                except Exception as e:
                    validation_error = _handle_validation_error(
                        current_state(), e, entity_type
                    )
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
            _auto_save_dataset(resolve_context())

            return json.dumps(
                {
                    "total": len(entity_list),
                    "created": sum(1 for r in results if r["status"] == "created"),
                    "failed": sum(1 for r in results if r["status"] == "error"),
                    "results": results,
                    "_dataset": _get_current_dataset_info(current_state()),
                },
                indent=2,
            )
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
