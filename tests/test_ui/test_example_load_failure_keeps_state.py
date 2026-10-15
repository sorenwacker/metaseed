"""A failed example load leaves the editor as it was.

The route reset the session and switched its profile before loading the spec
and validating the example, so a failure in either step returned an error after
the user's unsaved entities were already gone. A spec that failed to load also
escaped as an unhandled exception.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from metaseed.specs.loader import SpecLoadError
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _state_with_an_entity() -> AppState:
    state = AppState(profile="miappe", version="1.1")
    facade = state.get_or_create_facade()
    facade.add_entity("Investigation", {"unique_id": "inv-1", "title": "Unsaved"})
    return state


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("metaseed.ui.routes.examples.SpecLoader.load_profile", SpecLoadError("gone")),
        ("metaseed.ui.routes.examples.get_model", KeyError("Investigation")),
    ],
)
def test_a_failed_load_keeps_the_session(target: str, error: Exception) -> None:
    state = _state_with_an_entity()
    before = set(state.nodes_by_id)
    client = TestClient(create_app(state), raise_server_exceptions=False)

    with patch(target, side_effect=error):
        response = client.get("/load-example/miappe/1.2", follow_redirects=False)

    assert response.status_code in (400, 500)
    assert "detail" in response.json()
    assert (state.profile, state.version) == ("miappe", "1.1")
    assert set(state.nodes_by_id) == before
