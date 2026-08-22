"""The connection check names the cause of a failure, not just that one happened."""

from __future__ import annotations

import httpx
import pytest

from metaseed.seek.connection import check_connection, describe_failure


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_reachable_seek_reports_its_projects():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/projects"
        return httpx.Response(
            200,
            json={"data": [{"id": "1", "attributes": {"title": "Plants"}}]},
        )

    result = check_connection(
        {"url": "http://seek.test", "api_key": "k"}, http_client=_transport(handler)
    )
    assert result.ok
    assert result.projects == [("1", "Plants")]
    assert "1 project" in result.message


@pytest.mark.parametrize(
    ("status", "phrase"),
    [
        (401, "rejected the API key"),
        (403, "rejected the API key"),
        (503, "not serving SEEK"),
        (404, "not as a SEEK API"),
    ],
)
def test_http_failures_get_their_own_sentence(status, phrase):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="nope")

    result = check_connection(
        {"url": "http://seek.test"}, http_client=_transport(handler)
    )
    assert not result.ok
    assert phrase in result.message
    assert result.projects == []


def test_an_unanswered_host_is_not_blamed_on_the_key():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result = check_connection(
        {"url": "http://seek.test:9"}, http_client=_transport(handler)
    )
    assert not result.ok
    assert "Nothing answered at seek.test:9" in result.message
    assert "key" not in result.message


def test_a_missing_url_is_reported_without_a_request():
    result = check_connection({"url": ""})
    assert not result.ok
    assert "SEEK URL" in result.message


def test_name_resolution_failure_names_the_host():
    message = describe_failure(
        httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known"),
        "http://nowhere.invalid",
    )
    assert "resolve nowhere.invalid" in message
