"""Dataset management tools for MCP server."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from metaseed.agent.mcp.ui_session import DatasetManager, ui_datasets

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from metaseed.agent.mcp.context import MCPContext, ResolveContext
    from metaseed.agent.mcp.ui_session import AppState


def _get_dataset_manager(context: MCPContext) -> DatasetManager:
    """The dataset manager for the session a call is serving.

    Takes the context rather than resolving one: a manager built from a factory
    other than the caller's would send reads and writes to different
    repositories.

    Returns:
        A DatasetManager bound to that session's state.
    """
    manager: DatasetManager = context.dataset_factory.get_manager(context.state)
    return manager


def register_dataset_tools(  # noqa: C901
    mcp: FastMCP,
    resolve_context: ResolveContext,
) -> None:
    """Register dataset management tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        resolve_context: Returns the context for the call being served.
    """

    def current_state() -> AppState:
        """The state of the session this call is serving.

        Named to avoid colliding with the ``state`` locals several tools use.
        """
        return resolve_context().state

    @mcp.tool()
    def list_datasets() -> str:
        """List all saved datasets.

        Returns:
            JSON object with a ``datasets`` list (each with name, profile,
            version, entity_count, modified) and a ``count``.
        """
        try:
            manager = _get_dataset_manager(resolve_context())
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
        try:
            state = current_state()
            manager = _get_dataset_manager(resolve_context())
            result = manager.save_dataset(name)
            # Update state's current dataset so auto_save uses correct target
            ui_datasets.set_current_dataset_name(state, name)
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
        try:
            context = resolve_context()
            state = context.state
            # The caller's own repository: falling back to a default one here
            # would load a dataset from somewhere the caller never wrote to.
            repo = context.dataset_factory.sync_repo

            # Create fresh manager to avoid stale state issues
            manager = DatasetManager(repo, state)
            result = manager.load_dataset(name)

            # Explicitly update state's current dataset
            ui_datasets.set_current_dataset_name(state, name)

            # Do NOT recreate the facade here: manager.load_dataset already
            # rebuilt it with the loaded profile and entities, and discarding it
            # would drop everything that was just loaded.

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
        try:
            manager = _get_dataset_manager(resolve_context())
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
        try:
            state = current_state()

            # Prove the profile/version loads BEFORE touching the live
            # session: a typo'd profile name must cost an error message, not
            # the caller's unsaved entities and a state no tool can use.
            from metaseed.facade import ProfileFacade

            facade = ProfileFacade(profile, version)

            state.profile = profile
            state.version = version
            state.facade = None
            state.reset()
            state.facade = facade

            manager = _get_dataset_manager(resolve_context())
            manager.save_dataset(name)
            # Update state's current dataset so auto_save uses correct target
            ui_datasets.set_current_dataset_name(state, name)

            return json.dumps(
                {
                    "status": "created",
                    "name": name,
                    "profile": profile,
                    "version": version,
                    # `_spec` is set only when a caller passes a pre-loaded spec, so
                    # this was null on every real call; the facade knows the answer.
                    "root_entity": facade._root_entity(),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def import_from_database(profile: str, accession: str, name: str) -> str:
        """Import a public record from a source database and save it.

        Runs metaseed's registered importer for the profile, replaces the
        current dataset with the fetched record, and saves it under ``name``.
        The same adapter registry the web UI uses is consulted, so no importer
        is reimplemented here and a newly declared one is available at once.

        Args:
            profile: Profile to import into ("ena", "pride", "metabolights",
                or "miappe" for a BrAPI server).
            accession: The public accession (e.g. "MTBLS1", "PXD000001",
                "PRJEB1234") or, for "miappe", a BrAPI v2 server URL.
            name: Name to save the imported dataset under.

        Returns:
            JSON with the import status (profile, version, accession,
            entity_count), or an error naming the importable profiles.
        """
        from metaseed import adapters

        try:
            context = resolve_context()
            state = context.state

            try:
                info = ui_datasets.import_from_source(state, profile, accession)
            except ui_datasets.ImportSourceError as exc:
                return json.dumps(
                    {
                        "error": str(exc),
                        "available": list(adapters.importable_profiles()),
                    }
                )

            manager = _get_dataset_manager(context)
            manager.save_dataset(name)
            ui_datasets.set_current_dataset_name(state, name)

            return json.dumps(
                {
                    "status": "imported",
                    "name": name,
                    "accession": accession,
                    **info,
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
        try:
            state = current_state()

            # Count every entity, including nested children, so the per-type
            # breakdown is consistent with total_entities below.
            entity_counts: dict[str, int] = {}
            for node in state.nodes_by_id.values():
                etype = node.entity_type
                entity_counts[etype] = entity_counts.get(etype, 0) + 1

            return json.dumps(
                {
                    "dataset_name": ui_datasets.get_current_dataset_name(state),
                    "profile": state.profile,
                    "version": state.version,
                    "entity_counts": entity_counts,
                    "total_entities": len(state.nodes_by_id),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
