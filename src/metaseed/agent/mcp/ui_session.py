"""The MCP host's seam onto the editing session it shares with the web UI.

An MCP tool and a browser click edit *one* session: `create_entity` from an
agent and the entity form in the UI must land in the same dataset, and a save
from either must be visible to the other. The objects that session is made of —
``AppState`` and its ``TreeNode``s, ``EntityService``, ``DatasetManager`` and
the ``metaseed.ui.datasets`` helpers — live under ``metaseed.ui`` today, so the
MCP host depends on ``metaseed.ui``. That dependency is real, not accidental.

This module is where it is declared. Every other module under
``metaseed/agent/mcp/`` imports these names from here, so the edge appears once,
in an import graph, instead of ~25 times inside function bodies where nothing
could see it (ADR 004; ``tests/test_modularity.py`` enforces it).

The imports below are module level on purpose. ``metaseed.ui.__init__`` resolves
the FastAPI application lazily, so importing this module costs the session
classes and nothing else: the MCP server holds a session without a web server.

``metaseed.ui.datasets`` is re-exported as a module rather than as its
individual functions, so a call still resolves through the defining module the
way the function-level imports it replaces did.
"""

from __future__ import annotations

from metaseed.ui import datasets as ui_datasets
from metaseed.ui.dataset_manager import DatasetManager, DatasetManagerFactory
from metaseed.ui.services.entities import EntityService
from metaseed.ui.state import AppState, TreeNode

__all__ = [
    "AppState",
    "DatasetManager",
    "DatasetManagerFactory",
    "EntityService",
    "TreeNode",
    "ui_datasets",
]
