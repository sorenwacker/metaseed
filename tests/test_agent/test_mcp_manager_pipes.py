"""The spawned MCP server must not be able to deadlock on its own logging.

`Popen(stdout=PIPE, stderr=PIPE)` for a long-running uvicorn child, with the
pipes read only in the immediate-exit branch: a running server writes an
access-log line per request, and once the ~64KB OS pipe buffer fills, the
child's next write blocks and the server freezes mid-request. The classic
undrained-PIPE deadlock, guaranteed under normal sustained use.

The child now logs to a file under the user data dir. The fail-fast branch
reads the file tail instead of `communicate()`, so a server that dies on
startup still reports why.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from metaseed.agent.mcp.manager import MCPServerManager


@pytest.fixture(autouse=True)
def _fresh_manager():
    """MCPServerManager is a singleton; a fake process left in it by one test
    would make the next one's `is_running` short-circuit."""
    MCPServerManager._instance = None
    yield
    MCPServerManager._instance = None


def _fake_popen(poll_result: int | None):
    process = MagicMock()
    process.poll.return_value = poll_result
    process.pid = 4242
    return process


class TestNoPipes:
    def test_the_child_gets_a_log_file_not_pipes(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        manager = MCPServerManager()
        captured: dict = {}

        def record(cmd, **kwargs):
            captured.update(kwargs)
            return _fake_popen(None)

        with patch("subprocess.Popen", side_effect=record):
            manager.start(transport="http", host="127.0.0.1", port=8899)

        assert captured.get("stdout") is not subprocess.PIPE
        assert captured.get("stderr") is not subprocess.PIPE
        assert captured.get("stdout") is not None, "output must go somewhere readable"

    def test_a_child_that_dies_on_startup_still_reports_why(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        manager = MCPServerManager()

        def record(cmd, **kwargs):
            # Simulate the child writing its dying words to the log target.
            kwargs["stderr"].write("Address already in use\n")
            kwargs["stderr"].flush()
            return _fake_popen(1)

        with patch("subprocess.Popen", side_effect=record):
            status = manager.start(transport="http", host="127.0.0.1", port=8899)

        assert status.running is False
        assert "Address already in use" in (status.error or "")
