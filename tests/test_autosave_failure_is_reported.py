"""An auto-save that fails must be reported, not swallowed.

DatasetManager.auto_save caught ValueError and OSError with ``pass``, and the
MCP wrapper logged at debug level, so an edit that never reached disk was
reported to the UI and to an agent as a success.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _disk_full(self, name, data):
    raise OSError("No space left on device")


@pytest.fixture
def standalone_mcp():
    from metaseed.agent.mcp.server import reset_mcp_state

    reset_mcp_state()
    yield
    reset_mcp_state()


def test_mcp_create_entity_reports_a_failed_save(standalone_mcp, monkeypatch) -> None:
    from metaseed.agent.mcp.server import create_server

    tools = create_server()._tool_manager._tools
    assert "error" not in json.loads(
        tools["create_dataset"].fn(name="test-unsaved", profile="miappe", version="1.1")
    )
    monkeypatch.setattr(FilesystemDatasetRepository, "save", _disk_full)

    result = json.loads(
        tools["create_entity"].fn(
            entity_type="Investigation", data='{"title": "Unsaved"}'
        )
    )

    assert "error" not in result
    assert "No space left on device" in result["save_warning"]


def test_ui_create_route_reports_a_failed_save(monkeypatch) -> None:
    client = TestClient(create_app(AppState(profile="miappe", version="1.1")))
    monkeypatch.setattr(FilesystemDatasetRepository, "save", _disk_full)

    response = client.post(
        "/entity",
        data={
            "_entity_type": "Investigation",
            "unique_id": "INV-1",
            "title": "Unsaved",
        },
    )

    assert response.status_code == 200
    assert "not saved" in response.text
    assert "No space left on device" in response.text
