"""The metaseed app hosts no HTTP MCP server and shows no control for one.

MCP is used over stdio (``metaseed mcp`` from an agent's configuration); the
HTTP transport is the hub's concern. The in-app server the header button used
to spawn on port 8001 is gone, with its routes and its subprocess manager.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

_UI = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui"


def test_the_mcp_routes_are_gone():
    client = TestClient(create_app(AppState()))
    assert client.get("/api/mcp/status").status_code == 404
    assert client.post("/api/mcp/start").status_code in (404, 405)
    assert client.post("/api/mcp/stop").status_code in (404, 405)


def test_the_header_has_no_mcp_button():
    client = TestClient(create_app(AppState()))
    html = client.get("/").text
    assert 'data-testid="btn-mcp"' not in html
    assert "mcp.js" not in html
    assert not (_UI / "static" / "js" / "mcp.js").exists()


def test_no_subprocess_manager_remains():
    import importlib.util

    assert importlib.util.find_spec("metaseed.agent.mcp.manager") is None
