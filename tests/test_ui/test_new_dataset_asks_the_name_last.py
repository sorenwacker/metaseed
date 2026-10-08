"""New Dataset asks for the standard and its version first, and the name last.

The name field sat above the cards, where it read as a search box, and a
version button refused to work until it was filled. The cards come first now;
a version opens a screen of its own that names the choice and asks the name.
See docs/getting-started/quickstart.md, *Web UI*.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _client() -> TestClient:
    return TestClient(create_app(AppState()))


def test_the_cards_come_without_a_name_field() -> None:
    html = _client().get("/new-dataset").text

    assert 'data-testid="new-dataset-name"' not in html
    assert 'data-testid="profile-miappe-v1.2"' in html
    assert 'hx-get="/new-dataset/name?profile=miappe&version=1.2"' in html
    assert "validateDatasetName" not in html


def test_a_version_opens_the_name_step_for_that_choice() -> None:
    html = (
        _client()
        .get("/new-dataset/name", params={"profile": "miappe", "version": "1.2"})
        .text
    )

    assert 'data-testid="dataset-name-step"' in html
    assert ">MIAPPE v1.2<" in html
    assert 'data-testid="new-dataset-name"' in html
    assert 'name="profile" value="miappe"' in html
    assert 'name="version" value="1.2"' in html
    assert 'hx-get="/form/Investigation"' in html
    assert 'data-testid="btn-create-dataset"' in html
    assert 'data-testid="btn-choose-standard"' in html


def test_the_name_step_creates_the_dataset_under_that_name() -> None:
    """The step's form sends what the root entity's form took all along."""
    from metaseed.ui.datasets import get_current_dataset_name

    state = AppState()
    client = TestClient(create_app(state))

    page = client.get(
        "/form/Investigation",
        params={"profile": "miappe", "version": "1.2", "dataset": "test-named-last"},
    )

    assert page.status_code == 200
    # Saved with its first entity, as before; named from here on.
    assert get_current_dataset_name(state) == "test-named-last"
    assert (state.profile, state.version) == ("miappe", "1.2")


def test_a_version_the_profile_does_not_have_is_refused() -> None:
    client = _client()

    assert (
        client.get(
            "/new-dataset/name", params={"profile": "miappe", "version": "9.9"}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/new-dataset/name", params={"profile": "nope", "version": "1.0"}
        ).status_code
        == 404
    )
