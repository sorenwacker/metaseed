"""Entity management tools for MCP server.

Uses EntityService for all CRUD operations to avoid code duplication.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from metaseed.utils.json import DateAwareEncoder

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


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
    def create_entity(entity_type: str, data: str, parent_id: str | None = None) -> str:
        """Create a new entity in the current dataset.

        Creates an entity of the specified type with the provided data.
        If parent_id is provided:
        - Auto-fills the child's reference to the parent (e.g., Study.investigation_id)
        - Updates the parent's reference field to include the child

        Auto-saves the dataset after creation.

        Args:
            entity_type: Entity type (e.g., "Investigation", "Study").
            data: JSON string of field values.
            parent_id: Optional parent entity ID to create as child of.
                      Use this to build hierarchies (e.g., Study under Investigation).
                      The parent's reference field will be auto-updated.

        Returns:
            JSON with created entity info including parent relationship.
        """
        try:
            service = get_entity_service()
            entity_data = json.loads(data)
            result = service.create_entity(entity_type, entity_data, parent_id)

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

            return json.dumps(result, indent=2)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def update_entity(node_id: str, data: str) -> str:
        """Update an existing entity.

        Merges the provided data with the existing entity.
        Auto-saves the dataset after update.

        Args:
            node_id: The entity's node ID.
            data: JSON string of fields to update.

        Returns:
            JSON with updated entity info or error.
        """
        try:
            service = get_entity_service()
            updates = json.loads(data)
            result = service.update_entity(node_id, updates)
            return json.dumps(result, indent=2)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def delete_entity(node_id: str) -> str:
        """Delete an entity from the current dataset.

        Removes the entity and auto-saves the dataset.

        Args:
            node_id: The entity's node ID.

        Returns:
            JSON with deletion status.
        """
        try:
            service = get_entity_service()
            result = service.delete_entity(node_id)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def bulk_update_entities(updates: str) -> str:
        """Update multiple entities at once.

        Applies updates to multiple entities in a single operation.
        Auto-saves after all updates are applied.

        Args:
            updates: JSON array of updates, each with "id" and "data" fields.
                    Example: [{"id": "abc123", "data": {"title": "New Title"}}]

        Returns:
            JSON with results for each update.
        """
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

            return json.dumps(
                {
                    "total": len(update_list),
                    "updated": sum(1 for r in results if r["status"] == "updated"),
                    "errors": sum(1 for r in results if r["status"] == "error"),
                    "results": results,
                },
                indent=2,
            )
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
