"""Route tests for the SEEK export page — gated by the plugin feature switch."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.settings import Settings
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def make_client(tmp_path):
    def _make() -> tuple[TestClient, Settings, AppState]:
        state = AppState(profile="isa", version="1.0")
        app = create_app(state)
        settings = Settings(tmp_path / "settings.json")
        app.state.settings = settings
        return TestClient(app), settings, state

    return _make


def test_seek_page_empty_state_when_no_dataset(make_client):
    client, _settings, _state = make_client()  # seek enabled, empty dataset
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-empty"' in response.text
    assert 'data-testid="seek-export-disabled"' in response.text  # download disabled


def test_seek_page_shows_context_when_dataset_loaded(make_client):
    client, _settings, _state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-context"' in response.text
    assert "isa" in response.text  # profile shown
    assert "Investigation ×1" in response.text  # entity preview
    assert 'data-testid="seek-export-rdf"' in response.text  # download enabled


def test_seek_page_hidden_when_disabled(make_client):
    client, settings, _state = make_client()
    settings.set_adapter_enabled("seek", False)
    assert client.get("/seek").status_code == 404
    assert client.get("/seek/isa-rdf").status_code == 404


def test_isa_rdf_download_requires_a_dataset(make_client):
    client, _settings, _state = make_client()  # empty state
    assert client.get("/seek/isa-rdf").status_code == 400


def test_isa_rdf_exports_the_current_dataset(make_client):
    client, _settings, _state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    response = client.get("/seek/isa-rdf")
    assert response.status_code == 200
    assert "text/turtle" in response.headers["content-type"]
    assert "jerm:Investigation" in response.text
    assert response.headers["content-disposition"].endswith('-seek.ttl"')


def test_download_filename_is_sanitized(make_client):
    # A dataset name with quotes/unicode/newlines must not break the header.
    client, _settings, state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    from metaseed.ui.datasets import set_current_dataset_name

    set_current_dataset_name(state, 'ev"il\nΩ name')
    response = client.get("/seek/isa-rdf")
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.isascii()  # no latin-1 encode crash
    filename = disposition.split("filename=", 1)[1].strip('"')
    assert '"' not in filename and "\n" not in filename  # no header injection
    assert filename == "ev-il-name-seek.ttl"
