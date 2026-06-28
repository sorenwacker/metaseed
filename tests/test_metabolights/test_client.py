"""Tests for the MetaboLights web service client.

The request shape and JSON parsing are checked hermetically with a mock
transport. A live smoke test against the real MetaboLights API is marked
``network`` and skipped by the default test run.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from metaseed.metabolights.client import MetaboLightsClient

FIXTURE = Path(__file__).parent / "fixtures" / "study.json"


def test_study_builds_the_request_and_parses_the_document():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = MetaboLightsClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    document = client.study("MTBLS1")

    assert captured["url"].endswith("/studies/MTBLS1")
    assert "metaseed" in captured["user_agent"]  # EBI etiquette
    assert document["isaInvestigation"]["identifier"] == "MTBLS1"


def test_study_unwraps_a_content_envelope():
    payload = {"content": {"isaInvestigation": {"identifier": "MTBLS9"}}}
    client = MetaboLightsClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
        )
    )
    assert client.study("MTBLS9") == payload["content"]


def test_study_returns_empty_dict_for_non_object_payload():
    client = MetaboLightsClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=[]))
        )
    )
    assert client.study("MTBLS0") == {}


def test_study_raises_on_http_error():
    client = MetaboLightsClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(404))
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.study("MTBLS0")


@pytest.mark.network
def test_study_live_smoke():
    """Hit the real MetaboLights API (opt-in: ``-m network``)."""
    document = MetaboLightsClient().study("MTBLS1")
    assert isinstance(document, dict)
    investigation = document.get("isaInvestigation")
    if investigation:
        assert investigation.get("identifier") == "MTBLS1"
        assert isinstance(investigation.get("studies"), list)
