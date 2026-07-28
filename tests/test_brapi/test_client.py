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

from metaseed.brapi.client import BrapiClient, BrapiEndpointError

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
    assert "/brapi/v2/studies" in captured["url"]
    assert "page=0" in captured["url"]  # pagination params are sent
    assert "metaseed" in captured["user_agent"]


def test_get_follows_brapi_pagination():
    """records spread across pages are all collected, not just page 0."""
    pages = {
        "0": {
            "metadata": {"pagination": {"currentPage": 0, "totalPages": 2}},
            "result": {"data": [{"studyDbId": "a"}, {"studyDbId": "b"}]},
        },
        "1": {
            "metadata": {"pagination": {"currentPage": 1, "totalPages": 2}},
            "result": {"data": [{"studyDbId": "c"}]},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = dict(request.url.params).get("page", "0")
        return httpx.Response(200, json=pages[page])

    client = BrapiClient(
        BASE_URL, http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    rows = client.studies()
    assert [r["studyDbId"] for r in rows] == ["a", "b", "c"]


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
    """A server error still fails loudly - it is translated, not swallowed."""
    client = BrapiClient(
        BASE_URL,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(500))
        ),
    )
    with pytest.raises(BrapiEndpointError):
        client.studies()


@pytest.mark.network
def test_studies_live_smoke():
    """Hit a public BrAPI server (opt-in: ``-m network``)."""
    rows = BrapiClient(BASE_URL).studies()
    assert isinstance(rows, list)


class TestUnhelpfulErrorsAreTranslated:
    """A wrong address is the most common BrAPI failure, and its raw form names
    nothing: a server root without ``/brapi/v2`` 404s, and an HTML error page
    surfaces as ``Expecting value: line 1 column 1``. Neither says "wrong URL",
    and users reported being unable to get any endpoint working as a result."""

    def _client(self, base_url: str, handler) -> BrapiClient:
        transport = httpx.MockTransport(handler)
        return BrapiClient(base_url, http_client=httpx.Client(transport=transport))

    def test_a_server_root_without_the_api_path_says_to_add_it(self) -> None:
        client = self._client(
            "https://server.example.org",
            lambda request: httpx.Response(404, text="Not Found"),
        )

        with pytest.raises(BrapiEndpointError) as err:
            client.studies()

        message = str(err.value)
        assert "404" in message
        assert "/brapi/v2" in message, "the message must name the likely fix"

    def test_a_correct_looking_url_is_not_told_to_add_the_suffix(self) -> None:
        """A base URL that already ends in /brapi/v2 gets no misleading hint."""
        client = self._client(
            "https://server.example.org/brapi/v2",
            lambda request: httpx.Response(404, text="Not Found"),
        )

        with pytest.raises(BrapiEndpointError) as err:
            client.studies()

        assert "must be the BrAPI v2 root" not in str(err.value)

    def test_an_html_page_is_reported_as_not_being_an_endpoint(self) -> None:
        client = self._client(
            "https://server.example.org/germinate",
            lambda request: httpx.Response(
                200, text="<html>hello</html>", headers={"content-type": "text/html"}
            ),
        )

        with pytest.raises(BrapiEndpointError) as err:
            client.studies()

        assert "did not return JSON" in str(err.value)

    def test_a_protected_server_is_reported_as_needing_a_token(self) -> None:
        """Several public BrAPI servers answer 401; that is a missing token, not
        a missing dataset."""
        client = self._client(
            "https://server.example.org/brapi/v2",
            lambda request: httpx.Response(401, json={"metadata": {}}),
        )

        with pytest.raises(BrapiEndpointError) as err:
            client.studies()

        assert "token" in str(err.value)

    def test_a_working_server_still_returns_data(self) -> None:
        """The translation must not swallow success."""
        client = self._client(
            "https://server.example.org/brapi/v2",
            lambda request: httpx.Response(
                200,
                json={
                    "metadata": {"pagination": {"totalPages": 1}},
                    "result": {"data": [{"studyDbId": "1"}]},
                },
            ),
        )

        assert client.studies() == [{"studyDbId": "1"}]
