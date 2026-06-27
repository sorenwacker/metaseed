"""Graph visualization service.

Builds graph data (nodes and edges) from the AppState entity tree
for visualization with vis.js.

Note: The graph building logic is now implemented in ProfileFacade.to_graph().
This module provides a thin wrapper for backward compatibility with UI code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


def build_graph(state: AppState) -> dict[str, Any]:
    """Build graph data from entity tree.

    Delegates to facade.to_graph() for vis.js format generation.
    The facade handles:
    - Node generation with tooltips
    - Parent-child containment edges
    - Reference field edges (dashed)

    Also includes all entity types from the spec for legend generation,
    so the legend shows all possible types even if no instances exist.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Dictionary with 'nodes', 'edges', and 'entity_types' lists for vis.js.
    """
    facade = state.get_or_create_facade()
    graph_data = facade.to_graph()

    # Add all entity types from spec for legend (in spec order)
    entity_types = facade.entities
    graph_data["entity_types"] = entity_types

    return graph_data
