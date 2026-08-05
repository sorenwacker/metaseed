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
    assert 'data-testid="seek-sync-empty"' in response.text  # nothing to sync
    assert 'data-testid="seek-export-disabled"' in response.text  # download disabled
    assert 'data-testid="seek-needs-key"' in response.text  # no API key configured


def test_seek_page_shows_context_when_dataset_loaded(make_client):
    client, _settings, _state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    response = client.get("/seek")
    assert response.status_code == 200
    assert "isa" in response.text  # profile shown
    assert "Investigation ×1" in response.text  # entity preview  # noqa: RUF001
    assert 'data-testid="seek-export-rdf"' in response.text  # download enabled
    assert 'data-testid="seek-sync-form"' in response.text  # sync offered


def test_seek_page_disables_export_when_no_exportable_types(make_client):
    # A dataset made only of entities the FDS export never emits (e.g. Person)
    # must NOT show an enabled download that yields an empty file.
    client, _settings, state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Person", "identifier": "P1", "last_name": "Doe"},
    )
    assert [n.entity_type for n in state.nodes_by_id.values()] == ["Person"]
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-sync-empty"' in response.text
    assert 'data-testid="seek-export-disabled"' in response.text
    assert 'data-testid="seek-export-rdf"' not in response.text
    assert "Person ×1" not in response.text  # not in "Will emit"  # noqa: RUF001


def test_seek_page_hidden_when_disabled(make_client):
    client, settings, _state = make_client()
    settings.set_adapter_enabled("seek", False)
    assert client.get("/seek").status_code == 404
    assert client.get("/seek/isa-rdf").status_code == 404
    assert client.get("/seek/model-ttl").status_code == 404
    assert client.post("/seek/provision").status_code == 404
    assert client.post("/seek/sync").status_code == 404


def test_model_ttl_downloads_profile_definitions(make_client):
    client, _settings, _state = make_client()
    response = client.get("/seek/model-ttl")
    assert response.status_code == 200
    assert "text/turtle" in response.headers["content-type"]
    assert "rdf:Property" in response.text or "schema:valueRequired" in response.text
    assert response.headers["content-disposition"].endswith('-model.ttl"')


def test_model_ttl_honors_selected_profile(make_client):
    # A different profile can be exported than the active session profile.
    client, _settings, _state = make_client()  # active profile is isa
    response = client.get("/seek/model-ttl", params={"profile": "miappe"})
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('"miappe-model.ttl"')


def test_seek_page_offers_a_profile_selector(make_client):
    client, _settings, _state = make_client()
    page = client.get("/seek").text
    assert 'data-testid="seek-model-profile"' in page
    assert ">miappe</option>" in page and ">isa</option>" in page  # multiple profiles


def test_model_ttl_unknown_profile_does_not_reflect_input(make_client):
    # A crafted profile value must not be echoed back into the HTML response.
    client, _settings, _state = make_client()
    payload = "<script>alert(1)</script>"
    response = client.get("/seek/model-ttl", params={"profile": payload})
    assert response.status_code == 400
    assert payload not in response.text  # no reflected XSS
    assert "<script>" not in response.text


def test_provision_without_config_reports_error(make_client):
    # No SEEK url/key configured -> a readable error, not a crash or network call.
    client, _settings, _state = make_client()
    response = client.post("/seek/provision", data={"project_id": ""})
    assert response.status_code == 200
    assert 'data-testid="seek-action-error"' in response.text
    assert "SEEK URL" in response.text


def test_sync_without_dataset_reports_error(make_client):
    client, _settings, _state = make_client()  # empty dataset
    response = client.post("/seek/sync", data={"project_id": ""})
    assert response.status_code == 200
    assert 'data-testid="seek-action-error"' in response.text
    assert "No dataset" in response.text


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


def test_the_page_offers_one_profile_choice_not_two(make_client):
    """Two "Model (profile)" dropdowns could disagree -- provisioning one profile
    while handing an admin the Extended Metadata of another. There is now a single
    selector, and the Extended Metadata form mirrors it via a hidden field."""
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert html.count('id="seek-profile"') == 1
    assert html.count('id="seek-emt-profile"') == 1
    assert "Model (profile)" not in html  # the old, duplicated label is gone


def test_the_page_does_not_pass_a_default_profile_off_as_a_loaded_dataset(make_client):
    """The page reported "loaded now: <profile>", which was the app's default
    profile whether or not any dataset was open. The sync step now speaks to the
    actual dataset, and says plainly when none is loaded."""
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert "loaded now" not in html
    assert 'data-testid="seek-sync-empty"' in html
    assert "No dataset is loaded" in html


def test_the_page_avoids_the_worst_jargon(make_client):
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert "Idempotent" not in html and "idempotent" not in html
    assert "sample-bearing" not in html
    assert "closed value lists" not in html


def test_the_page_lets_you_choose_a_version(make_client):
    """Provisioning always used a profile's latest version, so a profile with
    several -- miappe 1.1/1.2 -- could not be set up at an older one, even when a
    dataset was built on it. The setup step now offers a version selector."""
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert 'data-testid="seek-model-version"' in html
    assert 'name="version"' in html


def test_the_model_download_honours_the_requested_version(make_client):
    """A version that is not the latest must actually load that version, not be
    silently replaced by the newest."""
    client, _settings, _state = make_client()

    v11 = client.get("/seek/model-ttl", params={"profile": "miappe", "version": "1.1"})
    v12 = client.get("/seek/model-ttl", params={"profile": "miappe", "version": "1.2"})

    assert v11.status_code == 200 and v12.status_code == 200
    # The two versions differ, so honouring the request produces different output;
    # ignoring it and loading the latest for both would make them identical.
    assert v11.content != v12.content
