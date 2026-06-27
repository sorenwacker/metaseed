"""Regression tests for #32: MCP session state must be consistent.

`get_mcp_state()` resolves either the injected context's state (when the
ContextVar is visible) or the standalone fallback. In an async MCP server the
ContextVar set by `set_context` is not always visible inside a per-request task,
so the two sources must point at the same AppState — otherwise a later call
falls back to a fresh, default-profile (`miappe`) state and silently operates
against the wrong profile.
"""

from __future__ import annotations

from metaseed.agent.mcp import server
from metaseed.agent.mcp.context import MCPContext
from metaseed.agent.mcp.server import get_mcp_state, reset_mcp_state, set_context
from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.dataset_manager import DatasetManagerFactory
from metaseed.ui.services.entities import EntityService
from metaseed.ui.state import AppState


def _context_for(state: AppState) -> MCPContext:
    """Build an MCPContext like the UI app does (ui/app.py)."""
    return MCPContext(
        state=state,
        get_entity_service=lambda: EntityService(MemoryEntityRepository(state)),
        dataset_factory=DatasetManagerFactory(),
    )


def test_state_consistent_when_contextvar_not_visible() -> None:
    """get_mcp_state returns the injected state even when the ContextVar is not
    visible in the current task (the #32 failure mode)."""
    reset_mcp_state()
    try:
        state = AppState(profile="darwin-core", version="1.0")
        set_context(_context_for(state))

        # Simulate a per-request async task where the ContextVar did not
        # propagate: _context_var.get() returns None, so resolution falls
        # through to the standalone source.
        server._context_var.set(None)

        resolved = get_mcp_state()
        assert resolved is state
        assert resolved.profile == "darwin-core"
        assert resolved.version == "1.0"
    finally:
        reset_mcp_state()


def test_profile_binding_survives_contextvar_loss() -> None:
    """A profile bound through the context is not lost to the default when a
    later call resolves via the standalone fallback."""
    reset_mcp_state()
    try:
        state = AppState()
        set_context(_context_for(state))
        # bind a non-default profile, as create_dataset would
        get_mcp_state().profile = "isa"
        get_mcp_state().version = "1.0"

        # ContextVar not visible on a subsequent call
        server._context_var.set(None)

        assert get_mcp_state().profile == "isa"
        assert get_mcp_state().version == "1.0"
    finally:
        reset_mcp_state()
