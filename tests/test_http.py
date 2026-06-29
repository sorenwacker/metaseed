"""Tests for the shared HTTP retry helper (metaseed._http)."""

from __future__ import annotations

import httpx
import pytest

from metaseed._http import request_json


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retries_a_503_then_succeeds():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    result = request_json(
        "https://x/", http_client=_client(handler), retries=3, backoff=0.0
    )
    assert result == {"ok": True}
    assert calls["n"] == 3  # two retries, then success


def test_retries_a_connection_timeout():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("boom", request=request)
        return httpx.Response(200, json=[])

    assert (
        request_json("https://x/", http_client=_client(handler), retries=2, backoff=0.0)
        == []
    )
    assert calls["n"] == 2


def test_raises_after_exhausting_retries():
    client = _client(lambda _r: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        request_json("https://x/", http_client=client, retries=2, backoff=0.0)


def test_does_not_retry_a_404():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        request_json("https://x/", http_client=_client(handler), retries=3, backoff=0.0)
    assert calls["n"] == 1  # 404 is not retryable
