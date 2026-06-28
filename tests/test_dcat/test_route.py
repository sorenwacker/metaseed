"""Smoke test for the /dcat viewer route."""

from __future__ import annotations

import pytest

pytest.importorskip("rdflib")

from fastapi.testclient import TestClient

from metaseed.ui import routes
from metaseed.ui.app import create_app


def test_dcat_route_renders_card_for_loaded_example():
    client = TestClient(create_app())
    # Populate the session with the shipped MIAPPE example.
    client.get("/load-example/miappe/1.2", follow_redirects=True)

    resp = client.get("/dcat")

    assert resp.status_code == 200
    body = resp.text
    assert "dcat:Dataset" in body  # Turtle
    assert "@context" in body  # JSON-LD
    assert "dct:title" in body


def test_dcat_api_returns_card_json():
    client = TestClient(create_app())
    client.get("/load-example/miappe/1.2", follow_redirects=True)

    resp = client.get("/api/dcat")

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"]  # the dataset's human title, not the storage name
    assert "dcat:Dataset" in data["turtle"]
    assert "@context" in data["jsonld"]


def test_dcat_api_returns_clean_error_instead_of_crashing(monkeypatch):
    """An unexpected failure in card building surfaces as a 500 JSON error,
    not an unhandled server exception."""

    def boom(_state):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(routes.dcat, "_build_card", boom)
    client = TestClient(create_app())

    resp = client.get("/api/dcat")

    assert resp.status_code == 500
    assert "kaboom" in resp.json()["error"]


def test_set_catalog_metadata_appears_in_card():
    """A record-rooted profile (Darwin Core) gets a real title once explicit
    catalog metadata is set via POST /api/dcat/metadata."""
    client = TestClient(create_app())
    client.get("/load-example/darwin-core/1.0", follow_redirects=True)

    # Before: no explicit metadata -> bare card (title falls back to identifier)
    set_resp = client.post(
        "/api/dcat/metadata",
        data={"title": "Bird occurrences 2024", "publisher": "GBIF node"},
    )
    assert set_resp.status_code == 200

    card = client.get("/api/dcat").json()
    assert card["title"] == "Bird occurrences 2024"
    assert "Bird occurrences 2024" in card["turtle"]
    assert "GBIF node" in card["turtle"]
    assert card["metadata"]["publisher"] == "GBIF node"
