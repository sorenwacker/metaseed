"""Tests for the ENA Portal client.

The request shape and JSON parsing are checked hermetically with a mock
transport. A live smoke test against the real ENA API is marked ``network`` and
skipped by the default test run.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from metaseed.ena.client import EnaClient

FIXTURE = Path(__file__).parent / "fixtures" / "read_run.json"


def test_read_run_builds_the_request_and_parses_rows():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = EnaClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    rows = client.read_run("PRJEB10000")

    assert len(rows) == 2
    assert "result=read_run" in captured["url"]
    assert "accession=PRJEB10000" in captured["url"]
    assert "fields=all" in captured["url"]  # every column ENA publishes
    assert "metaseed" in captured["user_agent"]  # EBI etiquette


def test_read_run_returns_empty_list_for_non_list_payload():
    client = EnaClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={}))
        )
    )
    assert client.read_run("PRJEB000") == []


def test_read_run_raises_on_http_error():
    client = EnaClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(500))
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.read_run("PRJEB10000")


@pytest.mark.network
def test_read_run_live_smoke():
    """Hit the real ENA Portal API (opt-in: ``-m network``)."""
    rows = EnaClient().read_run("ERR164407")
    assert isinstance(rows, list)
    if rows:
        assert "run_accession" in rows[0]
