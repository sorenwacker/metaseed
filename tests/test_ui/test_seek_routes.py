"""Route tests for the SEEK push page — gated by the feature switch.

Only the page visibility gating is tested here (no network / no live SEEK); the
actual push is covered by tests/test_seek/test_config.py (hermetic) and
test_live.py (network).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.settings import Settings
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def make_client(tmp_path):
    def _make() -> tuple[TestClient, Settings]:
        app = create_app(AppState())
        settings = Settings(tmp_path / "settings.json")
        app.state.settings = settings
        return TestClient(app), settings

    return _make


def test_seek_page_visible_when_enabled(make_client):
    client, _settings = make_client()  # seek enabled by default (httpx present)
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-push-form"' in response.text


def test_seek_page_hidden_when_disabled(make_client):
    client, settings = make_client()
    settings.set_adapter_enabled("seek", False)
    assert client.get("/seek").status_code == 404


def test_seek_push_rejected_when_disabled(make_client):
    client, settings = make_client()
    settings.set_adapter_enabled("seek", False)
    assert client.post("/seek/push", data={}).status_code == 404


def test_seek_push_validates_inputs_when_enabled(make_client):
    client, _settings = make_client()
    # Missing url/key -> 400 with an error partial, no network attempted.
    response = client.post("/seek/push", data={"profile": "isa/1.0"})
    assert response.status_code == 400
    assert "seek-push-error" in response.text
