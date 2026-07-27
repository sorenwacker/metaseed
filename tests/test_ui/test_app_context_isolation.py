"""Regression: building the UI app must not hijack the standalone MCP context.

The standalone MCP server (stdio) resolves state through the module-level
context. If `create_app()` installs a global MCP context at construction (and a
module-level `app = create_app()` runs that at import), merely importing the UI
replaces the MCP server's state — losing the session draft / dataset profile.
The context must be installed only when the app starts serving.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.agent.mcp import context, server
from metaseed.agent.mcp.server import get_mcp_state, reset_mcp_state
from metaseed.ui.app import create_app


def test_create_app_does_not_install_global_context_at_construction():
    reset_mcp_state()
    try:
        create_app()  # building the app must not touch the global MCP state
        assert context.default_context() is None
        assert server.get_context() is None
    finally:
        reset_mcp_state()


def test_serving_the_app_binds_mcp_state_to_the_ui_state():
    reset_mcp_state()
    try:
        app = create_app()
        with TestClient(app):  # entering runs the startup hook
            assert get_mcp_state() is app.state.ui_state
    finally:
        reset_mcp_state()
