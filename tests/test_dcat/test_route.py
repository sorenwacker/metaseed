"""Smoke test for the /dcat viewer route."""

from __future__ import annotations

import pytest

pytest.importorskip("rdflib")

from fastapi.testclient import TestClient

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
