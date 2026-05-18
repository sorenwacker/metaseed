"""Validation tools for MCP server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from metaseed.agent.core import ExtractionContext
from metaseed.specs.loader import SpecLoadError
from metaseed.utils.json import DateAwareEncoder

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_validation_tools(mcp: FastMCP, get_mcp_state) -> None:
    """Register validation tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        get_mcp_state: Function to get MCP state.
    """

    @mcp.tool()
    def validate_extracted(data: str, profile: str, version: str, entity: str) -> str:
        """Validate extracted data against the entity specification.

        Checks required fields, type constraints, and field-level validations.

        Args:
            data: JSON string of extracted instances.
            profile: Profile name.
            version: Profile version.
            entity: Entity name.

        Returns:
            JSON object with validation results for each instance.
        """
        try:
            instances = json.loads(data)
            if not isinstance(instances, list):
                instances = [instances]

            ctx = ExtractionContext.from_profile(profile, version)
            results = []

            for i, instance in enumerate(instances):
                errors = ctx.validate_instance(instance, entity)
                results.append(
                    {
                        "index": i,
                        "valid": len(errors) == 0,
                        "errors": [
                            {"field": e.field, "message": e.message, "value": e.value}
                            for e in errors
                        ],
                    }
                )

            return json.dumps(
                {
                    "total": len(instances),
                    "valid": sum(1 for r in results if r["valid"]),
                    "invalid": sum(1 for r in results if not r["valid"]),
                    "results": results,
                },
                indent=2,
            )

        except (json.JSONDecodeError, SpecLoadError) as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def validate_entity(node_id: str) -> str:
        """Validate a single entity against its specification.

        Checks the entity data against all field validations
        and cross-entity rules.

        Args:
            node_id: The entity's node ID.

        Returns:
            JSON with validation results.
        """
        state = get_mcp_state()

        try:
            node = state.nodes_by_id.get(node_id)
            if not node:
                return json.dumps({"error": f"Entity not found: {node_id}"})

            if not node.instance:
                return json.dumps({"error": "Entity has no instance data"})

            facade = state.get_or_create_facade()

            # Validate via Pydantic
            helper = getattr(facade, node.entity_type, None)
            if not helper:
                return json.dumps({"error": f"Unknown entity type: {node.entity_type}"})

            data = node.instance.model_dump(exclude_none=True)
            errors = []

            # Check required fields
            for field in helper._spec.fields:
                if field.required and field.name not in data:
                    errors.append(
                        {
                            "field": field.name,
                            "message": "Required field missing",
                            "value": None,
                        }
                    )

            return json.dumps(
                {
                    "id": node.id,
                    "entity_type": node.entity_type,
                    "valid": len(errors) == 0,
                    "errors": errors,
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def validate_dataset() -> str:
        """Validate all entities in the current dataset.

        Runs validation on all entities and reports any issues found.

        Returns:
            JSON with validation summary and detailed results.
        """
        state = get_mcp_state()

        try:
            facade = state.get_or_create_facade()
            results = []

            for node in state.entity_tree:
                _validate_node_recursive(node, facade, results)

            return json.dumps(
                {
                    "total": len(results),
                    "valid": sum(1 for r in results if r["valid"]),
                    "invalid": sum(1 for r in results if not r["valid"]),
                    "results": results,
                },
                indent=2,
                cls=DateAwareEncoder,
            )

        except Exception as e:
            return json.dumps({"error": str(e)})


def _validate_node_recursive(node, facade, results: list) -> None:
    """Recursively validate a node and its children.

    Args:
        node: TreeNode to validate.
        facade: ProfileFacade instance.
        results: List to append results to.
    """
    errors = []

    if node.instance:
        helper = getattr(facade, node.entity_type, None)
        if helper:
            data = node.instance.model_dump(exclude_none=True)
            for field in helper._spec.fields:
                if field.required and field.name not in data:
                    errors.append(
                        {
                            "field": field.name,
                            "message": "Required field missing",
                        }
                    )

    results.append(
        {
            "id": node.id,
            "entity_type": node.entity_type,
            "label": node.label,
            "valid": len(errors) == 0,
            "errors": errors,
        }
    )

    for child in node.children:
        _validate_node_recursive(child, facade, results)
