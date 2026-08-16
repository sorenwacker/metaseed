"""Only an MCP server on our port may be killed (260816 review).

`start()` treated any listener on the port as an orphan of its own: it read
whatever PID `lsof` reported and sent SIGTERM then SIGKILL, without checking
what the process was. `POST /api/mcp/start` is an unauthenticated local route,
so one click could kill an unrelated local process that happened to hold 8001 —
another dev server, a database tunnel, someone else's app.

`_check_mcp_responding` already exists to answer "is this our server". It just
was not asked before killing.
"""

from __future__ import annotations

from metaseed.agent.mcp.manager import MCPServerManager


def test_a_listener_that_is_not_an_mcp_server_is_not_killed(monkeypatch) -> None:
    manager = MCPServerManager()
    killed: list[int] = []

    monkeypatch.setattr(manager, "_check_port_in_use", lambda port: 4321)
    monkeypatch.setattr(manager, "_check_mcp_responding", lambda host, port: False)
    monkeypatch.setattr(
        manager, "kill_orphaned", lambda port=8001: killed.append(port) or True
    )

    status = manager.start(transport="streamable-http", host="127.0.0.1", port=8001)

    assert killed == [], "killed a process that is not an MCP server"
    assert not status.running
    assert "in use" in str(status.error).lower(), status


def test_our_own_orphan_is_still_cleaned_up(monkeypatch) -> None:
    """The case the kill exists for must keep working."""
    manager = MCPServerManager()
    killed: list[int] = []

    monkeypatch.setattr(manager, "_check_port_in_use", lambda port: 4321)
    monkeypatch.setattr(manager, "_check_mcp_responding", lambda host, port: True)
    monkeypatch.setattr(manager, "is_running", lambda port=8001: False)
    monkeypatch.setattr(
        manager, "kill_orphaned", lambda port=8001: killed.append(port) or True
    )
    monkeypatch.setattr(
        "subprocess.Popen", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop"))
    )

    manager.start(transport="streamable-http", host="127.0.0.1", port=8001)

    assert killed == [8001], "an orphaned MCP server was left holding the port"
