"""MCP context for dependency injection.

Provides explicit dependencies for MCP tools without globals.
The context is created during app initialization and passed to all tools.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.ui.dataset_manager import DatasetManagerFactory
    from metaseed.ui.services.entities import EntityService
    from metaseed.ui.state import AppState


@dataclass
class MCPContext:
    """Explicit dependencies for MCP tools.

    This dataclass holds all dependencies needed by MCP tools,
    eliminating the need for module-level globals. It ensures
    that all tools operate on the same state instance.

    Attributes:
        state: The shared AppState instance.
        get_entity_service: Factory function that returns a fresh EntityService.
            Called on each tool invocation to ensure the service uses current state.
        dataset_factory: Factory for creating DatasetManager instances tied to state.
    """

    state: AppState
    get_entity_service: Callable[[], EntityService]
    dataset_factory: DatasetManagerFactory
