"""UI tests for adapter file exports (ENA / PRIDE / MetaboLights / ISA-Tab)."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.routes.import_export import export_options_for_profile
from metaseed.ui.state import AppState


def test_export_options_are_profile_specific():
    """Each profile is offered its own repository format, plus the DCAT
    catalogue record, which describes a dataset under any profile."""
    assert {o["key"] for o in export_options_for_profile("ena")} == {"ena", "dcat"}
    assert {o["key"] for o in export_options_for_profile("pride")} == {"pride", "dcat"}
    assert {o["key"] for o in export_options_for_profile("metabolights")} == {
        "metabolights",
        "dcat",
    }
    # A profile with no repository adapter is offered no repository format —
    # only the universal record, never another profile's exporter.
    assert {o["key"] for o in export_options_for_profile("darwin-core")} == {"dcat"}


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


def test_export_route_rejects_a_format_not_offered_for_the_profile() -> None:
    """The route must gate on the same predicate that renders the buttons.

    Ungated, a hand-typed format ran an exporter against a profile it was never
    meant for and returned a 200 zip of header-only files.
    """
    from metaseed.ui.app import create_app
    from metaseed.ui.state import AppState

    state = AppState()
    state.profile = "darwin-core"
    state.version = "1.0"
    client = TestClient(create_app(state))

    response = client.get("/export/adapter/metabolights")

    assert response.status_code == 404, (
        "a metabolights export must not be offered for a darwin-core dataset"
    )


def test_dataset_page_offers_the_profiles_adapter_exports() -> None:
    """Adapter exports must be reachable from the dataset page, not only the
    entity form.

    Previously ``export_options`` was passed from a single route (the response
    after saving an entity), so the buttons appeared once and vanished as soon
    as the user navigated -- effectively undiscoverable.
    """
    from metaseed.ui.state import AppState

    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)

    response = client.get("/load-example/pride/1.0")

    assert response.status_code == 200
    assert 'data-testid="btn-export-pride"' in response.text
    # One control for the submission, not one per document in it.
    assert 'data-testid="btn-export-pride-sdrf"' not in response.text


def test_dataset_page_offers_no_exports_for_a_profile_without_any() -> None:
    """A profile with no declared export actions shows no adapter buttons."""
    from metaseed.ui.state import AppState

    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)

    response = client.get("/load-example/darwin-core/1.0")

    assert response.status_code == 200
    assert "btn-export-metabolights" not in response.text
