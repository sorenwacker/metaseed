"""Bad user input to the explore routes is a 400, not a 500.

The three explore handlers mapped ValueError (user-selected profiles) to 500
while the sibling /api/merge maps it to 400, and a submitted spec without a
"/" was silently dropped, so a fully malformed selection reached compare([])
and surfaced as a 500 with a misleading message.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(AppState()))


def test_a_spec_without_a_slash_is_rejected_not_dropped(client) -> None:
    response = client.post("/explore/compare", data={"profiles": ["miappe"]})
    assert response.status_code == 400
    assert "miappe" in response.json()["error"]


def test_an_unknown_profile_is_the_callers_mistake(client) -> None:
    response = client.post(
        "/explore/compare", data={"profiles": ["nope/1.0", "miappe/1.1"]}
    )
    assert response.status_code == 400


def test_graph_route_maps_bad_input_to_400(client) -> None:
    response = client.get("/explore/graph/nope")
    assert response.status_code == 400


def test_report_route_maps_bad_input_to_400(client) -> None:
    response = client.get("/explore/report/markdown/nope")
    assert response.status_code == 400
