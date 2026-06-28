"""End-to-end: import_accession wires the client and mapper together."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from metaseed.ena import import_accession
from metaseed.ena.client import EnaClient

FIXTURE = Path(__file__).parent / "fixtures" / "read_run.json"


def _mock_client() -> EnaClient:
    payload = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
    return EnaClient(http_client=httpx.Client(transport=transport))


def test_import_accession_builds_an_ena_dataset():
    client = import_accession("PRJEB10000", client=_mock_client())

    assert client.profile == "ena"
    types = {e["_type"] for e in client.serialize()["entities"]}
    assert {"Study", "Sample", "Experiment", "Run", "File"} <= types
