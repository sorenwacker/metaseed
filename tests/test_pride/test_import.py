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
    # A tree, not a single node: every record the API returns is its own
    # entity, so a user can open and edit them one at a time.
    assert {e["_type"] for e in entities} == {
        "Dataset",
        "Species",
        "Instrument",
        "Modification",
        "Contact",
        "Publication",
        "Sample",
        "DataFile",
    }

    dataset = entities[0]
    assert dataset["accession"] == "PXD000001"

    by_type: dict[str, list[dict]] = {}
    for entity in entities:
        by_type.setdefault(entity["_type"], []).append(entity)
    assert len(by_type["DataFile"]) == 3
    assert len(by_type["Contact"]) == 2
    assert by_type["Species"][0]["name"] == "Erwinia carotovora"
