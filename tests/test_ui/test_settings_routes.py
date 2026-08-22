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


def test_seek_row_shows_config_form_and_action_link(client):
    page = client.get("/settings").text
    assert 'data-testid="config-seek"' in page  # config form present
    assert 'data-testid="config-seek-api_key"' in page  # api key field
    assert 'data-testid="link-seek-action"' in page  # Open action link


def test_config_saves_and_masks_secret(client):
    response = client.post(
        "/settings/adapters/seek/config",
        data={"url": "http://localhost:3001", "api_key": "s3cret"},
    )
    assert response.status_code == 200
    # url is prefilled back; the api key is never rendered into the response.
    assert "http://localhost:3001" in response.text
    assert "s3cret" not in response.text
    assert "configured — leave blank to keep" in response.text


def test_config_unknown_adapter_is_404(client):
    assert client.post("/settings/adapters/nope/config", data={}).status_code == 404


def test_config_blank_secret_keeps_stored_key(client):
    settings = client.app.state.settings
    client.post(
        "/settings/adapters/seek/config",
        data={"url": "http://localhost:3001", "api_key": "keepme"},
    )
    # Re-submit with the api_key field blank (the UI never prefills a secret).
    client.post("/settings/adapters/seek/config", data={"url": "http://elsewhere:3001"})
    config = settings.get_adapter_config("seek")
    assert config["api_key"] == "keepme"  # secret retained
    assert config["url"] == "http://elsewhere:3001"  # plain field updated


def test_config_refused_when_adapter_disabled(client):
    settings = client.app.state.settings
    settings.set_adapter_enabled("seek", False)
    client.post("/settings/adapters/seek/config", data={"url": "http://x:3001"})
    assert settings.get_adapter_config("seek") == {}  # nothing persisted


def _configure_seek(client, monkeypatch, result):
    import metaseed.ui.routes.settings as settings_routes

    client.post(
        "/settings/adapters/seek/config",
        data={"url": "http://seek.test", "api_key": "k"},
    )
    monkeypatch.setattr(
        settings_routes, "run_adapter_check", lambda _info, _config: result
    )


def test_seek_row_offers_a_connection_check(client):
    page = client.get("/settings").text
    assert 'data-testid="check-seek"' in page


def test_check_reports_success_and_offers_the_projects(client, monkeypatch):
    from metaseed.seek.connection import ConnectionCheck

    _configure_seek(
        client,
        monkeypatch,
        ConnectionCheck(
            ok=True,
            message="Connected: 2 projects visible.",
            projects=[("1", "Plants"), ("2", "Soil")],
        ),
    )
    response = client.post("/settings/adapters/seek/check")
    assert response.status_code == 200
    assert 'data-testid="check-seek-ok"' in response.text
    assert "2 projects visible" in response.text
    assert 'data-testid="config-seek-project_id"' in response.text
    assert "Plants" in response.text and "Soil" in response.text


def test_check_reports_the_specific_failure(client, monkeypatch):
    from metaseed.seek.connection import ConnectionCheck

    _configure_seek(
        client,
        monkeypatch,
        ConnectionCheck(ok=False, message="SEEK rejected the API key.", projects=[]),
    )
    response = client.post("/settings/adapters/seek/check")
    assert 'data-testid="check-seek-error"' in response.text
    assert "rejected the API key" in response.text
    assert 'data-testid="config-seek-project_id"' not in response.text


def test_check_on_an_adapter_without_a_check_is_404(client):
    assert client.post("/settings/adapters/dcat/check").status_code == 404


def test_project_choice_is_saved_with_the_config(client):
    client.post(
        "/settings/adapters/seek/config",
        data={"url": "http://seek.test", "api_key": "k", "project_id": "2"},
    )
    settings = client.app.state.settings
    assert settings.get_adapter_config("seek")["project_id"] == "2"
    assert "Project: 2" in client.get("/settings").text
