"""Dataset management tools for MCP server."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_dataset_tools(mcp: FastMCP, get_mcp_state, reset_entity_service) -> None:
    """Register dataset management tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        get_mcp_state: Function to get MCP state.
        reset_entity_service: Function to reset entity service after dataset change.
    """

    @mcp.tool()
    def list_datasets() -> str:
        """List all saved datasets.

        Returns:
            JSON array of dataset names.
        """
        from metaseed.ui.dataset_manager import get_manager

        try:
            state = get_mcp_state()
            manager = get_manager(state)
            datasets = [asdict(d) for d in manager.list_datasets()]
            return json.dumps(
                {
                    "datasets": datasets,
                    "count": len(datasets),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def save_dataset(name: str) -> str:
        """Save the current entities to a named dataset.

        Creates or overwrites a dataset file with all current entities.

        Args:
            name: Name for the dataset (alphanumeric, hyphens, underscores).

        Returns:
            JSON with save status and dataset info.
        """
        from metaseed.ui.dataset_manager import get_manager

        try:
            state = get_mcp_state()
            manager = get_manager(state)
            result = manager.save_dataset(name)
            return json.dumps(
                {
                    "status": "saved",
                    **asdict(result),
                },
                indent=2,
            )
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def load_dataset(name: str) -> str:
        """Load a dataset into the editor.

        Loads entities from the saved dataset file and makes them available
        for viewing and editing.

        Args:
            name: Name of the dataset to load.

        Returns:
            JSON with loaded dataset info or error.
        """
        from metaseed.ui.dataset_manager import get_manager

        try:
            state = get_mcp_state()
            manager = get_manager(state)
            result = manager.load_dataset(name)
            reset_entity_service()
            return json.dumps(
                {
                    "status": "loaded",
                    **asdict(result),
                },
                indent=2,
            )
        except FileNotFoundError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def delete_dataset(name: str) -> str:
        """Delete a saved dataset.

        Permanently removes a dataset file.

        Args:
            name: Name of the dataset to delete.

        Returns:
            JSON with deletion status.
        """
        from metaseed.ui.dataset_manager import get_manager

        try:
            state = get_mcp_state()
            manager = get_manager(state)
            deleted = manager.delete_dataset(name)
            return json.dumps(
                {
                    "status": "deleted" if deleted else "not_found",
                    "name": name,
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def create_dataset(name: str, profile: str, version: str) -> str:
        """Create a new empty dataset with a specific profile.

        Creates a new dataset and sets up the editor with the specified
        metadata profile and version.

        Args:
            name: Name for the new dataset.
            profile: Profile name (e.g., "miappe", "darwin-core").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with created dataset info or error.
        """
        from metaseed.ui.dataset_manager import get_manager

        try:
            state = get_mcp_state()
            state.profile = profile
            state.version = version
            state.facade = None
            state.reset()

            facade = state.get_or_create_facade()

            manager = get_manager(state)
            manager.save_dataset(name)
            reset_entity_service()

            return json.dumps(
                {
                    "status": "created",
                    "name": name,
                    "profile": profile,
                    "version": version,
                    "root_entity": facade._spec.root_entity if facade._spec else None,
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_dataset_info() -> str:
        """Get information about the current dataset.

        Returns the current profile, version, and entity counts.

        Returns:
            JSON with current dataset information.
        """
        from metaseed.ui.dataset_manager import get_manager

        try:
            state = get_mcp_state()
            manager = get_manager(state)

            entity_counts: dict[str, int] = {}
            for node in state.entity_tree:
                etype = node.entity_type
                entity_counts[etype] = entity_counts.get(etype, 0) + 1

            return json.dumps(
                {
                    "dataset_name": manager.current_dataset,
                    "profile": state.profile,
                    "version": state.version,
                    "entity_counts": entity_counts,
                    "total_entities": len(state.nodes_by_id),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
