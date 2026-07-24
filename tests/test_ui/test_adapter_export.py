"""UI tests for adapter file exports (ENA / PRIDE / MetaboLights / ISA-Tab)."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.routes.import_export import export_options_for_profile
from metaseed.ui.state import AppState


def test_export_options_are_profile_specific():
    assert [o["key"] for o in export_options_for_profile("ena")] == ["ena"]
    assert [o["key"] for o in export_options_for_profile("pride")] == [
        "pride",
        "pride-sdrf",
    ]
    assert [o["key"] for o in export_options_for_profile("metabolights")] == [
        "metabolights"
    ]
    # A profile with no exporter offers nothing rather than a broken button.
    assert export_options_for_profile("darwin-core") == []


def test_adapter_export_returns_zip_of_files():
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/ena/1.0")

    response = client.get("/export/adapter/ena")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert "study.xml" in names and "sample.xml" in names


def test_adapter_export_unknown_format_is_404():
    client = TestClient(create_app(AppState()))
    assert client.get("/export/adapter/nope").status_code == 404


def test_export_button_renders_for_matching_profile():
    # Creating an ENA entity returns the edit form, which must offer the ENA
    # export download and not an unrelated one.
    state = AppState(profile="ena", version="1.0")
    client = TestClient(create_app(state))
    response = client.post(
        "/entity",
        data={"_entity_type": "Study", "alias": "S1", "title": "My study"},
    )
    assert response.status_code == 200
    assert 'data-testid="btn-export-ena"' in response.text
    assert 'data-testid="btn-export-metabolights"' not in response.text
