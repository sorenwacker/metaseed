"""End-to-end: import_accession wires the client and mapper together."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from metaseed.pride import import_accession
from metaseed.pride.client import PrideClient

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_client() -> PrideClient:
    project = json.loads((FIXTURES / "project.json").read_text())
    files = json.loads((FIXTURES / "files.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=files)
        return httpx.Response(200, json=project)

    return PrideClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_import_accession_builds_a_pride_dataset():
    client = import_accession("PXD000001", client=_mock_client())

    assert client.profile == "pride"
    entities = client.serialize()["entities"]
    assert {e["_type"] for e in entities} == {"Dataset"}

    dataset = entities[0]
    assert dataset["accession"] == "PXD000001"
    assert len(dataset["files"]) == 3
    assert len(dataset["contacts"]) == 2
    assert dataset["species"][0]["name"] == "Erwinia carotovora"
