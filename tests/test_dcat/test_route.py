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
