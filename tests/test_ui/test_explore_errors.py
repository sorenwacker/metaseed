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


def test_the_explorer_page_has_a_place_for_validation_rules_and_the_graph_carries_them():
    # "The explorers don't show all details and rules": the page now renders a
    # sidebar rules section, and the graph data it fetches carries each
    # profile's rules and each field's details for the entity panel.
    from fastapi.testclient import TestClient

    from metaseed.ui.app import create_app
    from metaseed.ui.state import AppState

    client = TestClient(create_app(AppState()))
    page = client.get("/explore/").text
    assert 'data-testid="explore-rules"' in page
    assert "renderRule(" in page and "renderFieldDetails(" in page
    graph = client.get("/explore/graph/isa/1.0").json()
    assert "rules" in graph
    node = next(n for n in graph["nodes"] if n["data"].get("name") == "Investigation")
    assert "rules" in node["data"]
    assert all("details" in f for f in node["data"]["fields"])


def test_a_bad_profile_name_in_a_report_request_comes_back_as_text_not_markup():
    # The 400 quotes what the caller sent. As HTML that was a reflected script;
    # as text the browser shows it and runs nothing.
    from fastapi.testclient import TestClient

    from metaseed.ui.app import create_app
    from metaseed.ui.state import AppState

    client = TestClient(create_app(AppState()))
    response = client.get("/explore/report/markdown/<img src=x onerror=alert(1)>")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/plain")
    assert "onerror" in response.text, "the caller still sees what was refused"


def test_a_profile_pick_and_a_page_label_do_not_build_markup_from_values():
    # The select value goes into a URL; the profile key goes into innerHTML.
    # Both are encoded on the way, and this keeps them so.
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui"
    core = (root / "static" / "js" / "core.js").read_text()
    assert "'/profile/' + encodeURIComponent(profile)" in core
    explore = (root / "templates" / "explore" / "index.html").read_text()
    assert "${escapeHtml(profiles[0])}" in explore
    assert "${profiles[0]}" not in explore
