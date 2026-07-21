"""Route tests for the Plugins settings page (hermetic, tmp-backed settings)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.settings import Settings
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def client(tmp_path):
    app = create_app(AppState())
    app.state.settings = Settings(tmp_path / "settings.json")
    return TestClient(app)


def test_settings_page_lists_all_adapters(client):
    response = client.get("/settings")
    assert response.status_code == 200
    for key in ("ena", "pride", "brapi", "metabolights", "dcat", "seek"):
        assert f"adapter-{key}" in response.text


def test_toggle_disables_then_reenables(client):
    # seek is enabled by default (httpx present); toggle it off, then on.
    off = client.post("/settings/adapters/seek/toggle")
    assert off.status_code == 200
    assert "Disabled" in off.text

    on = client.post("/settings/adapters/seek/toggle")
    assert on.status_code == 200
    assert "Enabled" in on.text


def test_toggle_unknown_adapter_is_404(client):
    assert client.post("/settings/adapters/nope/toggle").status_code == 404
