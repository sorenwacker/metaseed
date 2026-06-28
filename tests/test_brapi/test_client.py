"""Tests for the BrAPI client.

The request shape and JSON parsing are checked hermetically with a mock
transport. A live smoke test against a public BrAPI server is marked ``network``
and skipped by the default test run.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from metaseed.brapi.client import BrapiClient

FIXTURE = Path(__file__).parent / "fixtures" / "brapi.json"
BASE_URL = "https://test-server.brapi.org/brapi/v2"


def _payloads():
    return json.loads(FIXTURE.read_text())


def _mock_client(token: str | None = None) -> tuple[BrapiClient, dict]:
    payloads = _payloads()
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["user_agent"] = request.headers.get("user-agent", "")
        captured["authorization"] = request.headers.get("authorization", "")
        key = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=payloads[key])

    transport = httpx.MockTransport(handler)
    client = BrapiClient(
        BASE_URL, token=token, http_client=httpx.Client(transport=transport)
    )
    return client, captured


def test_studies_builds_request_and_parses_data():
    client, captured = _mock_client()
    rows = client.studies()

    assert isinstance(rows, list)
    assert len(rows) == 2
    assert captured["url"].endswith("/brapi/v2/studies")
    assert "metaseed" in captured["user_agent"]


def test_observation_units_sends_study_filter():
    client, captured = _mock_client()
    rows = client.observation_units("1001")

    assert len(rows) == 2
    assert "studyDbId=1001" in captured["url"]
    assert "/observationunits" in captured["url"]


def test_bearer_token_is_sent_when_given():
    client, captured = _mock_client(token="secret-token")  # noqa: S106
    client.germplasm()
    assert captured["authorization"] == "Bearer secret-token"


def test_no_authorization_header_without_token():
    client, captured = _mock_client()
    client.germplasm()
    assert captured["authorization"] == ""


def test_returns_empty_list_for_missing_result():
    client = BrapiClient(
        BASE_URL,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={}))
        ),
    )
    assert client.studies() == []


def test_raises_on_http_error():
    client = BrapiClient(
        BASE_URL,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(500))
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.studies()


@pytest.mark.network
def test_studies_live_smoke():
    """Hit a public BrAPI server (opt-in: ``-m network``)."""
    rows = BrapiClient(BASE_URL).studies()
    assert isinstance(rows, list)
