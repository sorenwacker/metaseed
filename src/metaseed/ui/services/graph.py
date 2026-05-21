"""Graph visualization service.

Builds graph data (nodes and edges) from the AppState entity tree
for visualization with vis.js.

Note: The graph building logic is now implemented in ProfileFacade.to_graph().
This module provides a thin wrapper for backward compatibility with UI code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


def build_graph(state: AppState) -> dict:
    """Build graph data from entity tree.

    Delegates to facade.to_graph() for vis.js format generation.
    The facade handles:
    - Node generation with tooltips
    - Parent-child containment edges
    - Reference field edges (dashed)

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Dictionary with 'nodes' and 'edges' lists for vis.js.
    """
    facade = state.get_or_create_facade()
    return facade.to_graph()
