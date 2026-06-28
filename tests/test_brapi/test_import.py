"""End-to-end: import_brapi wires the client and mapper together."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from metaseed.brapi import import_brapi
from metaseed.brapi.client import BrapiClient

FIXTURE = Path(__file__).parent / "fixtures" / "brapi.json"
BASE_URL = "https://test-server.brapi.org/brapi/v2"


def _mock_client() -> BrapiClient:
    payloads = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=payloads[key])

    transport = httpx.MockTransport(handler)
    return BrapiClient(BASE_URL, http_client=httpx.Client(transport=transport))


def test_import_brapi_builds_a_miappe_dataset():
    client = import_brapi(BASE_URL, client=_mock_client())

    assert client.profile == "miappe"
    types = {e["_type"] for e in client.serialize()["entities"]}
    assert {
        "Investigation",
        "Study",
        "BiologicalMaterial",
        "ObservationUnit",
        "ObservedVariable",
        "DataFile",
    } <= types


def test_import_brapi_filters_to_one_study():
    client = import_brapi(BASE_URL, study_db_id="1001", client=_mock_client())

    studies = [e for e in client.serialize()["entities"] if e["_type"] == "Study"]
    assert {s["unique_id"] for s in studies} == {"1001"}
