"""End-to-end: import_accession wires the client and mapper together."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from metaseed.metabolights import import_accession
from metaseed.metabolights.client import MetaboLightsClient

FIXTURE = Path(__file__).parent / "fixtures" / "study.json"


def _mock_client() -> MetaboLightsClient:
    payload = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
    return MetaboLightsClient(http_client=httpx.Client(transport=transport))


def test_import_accession_builds_a_metabolights_dataset():
    client = import_accession("MTBLS1", client=_mock_client())

    assert client.profile == "metabolights"
    types = {e["_type"] for e in client.serialize()["entities"]}
    assert {
        "Investigation",
        "Person",
        "Publication",
        "Study",
        "Factor",
        "Protocol",
        "Sample",
        "Assay",
        "DataFile",
    } <= types
