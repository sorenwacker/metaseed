"""Hermetic tests for SeekClient using a mock httpx transport.

The JSON:API request shapes are checked against a mock transport that records
each POST and returns a SEEK-shaped ``{"data": {"id": ...}}`` response, so no
network or running SEEK is needed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from metaseed.seek.client import SeekClient


class _RecordingSeek:
    """A mock SEEK: records requests, hands out incrementing ids per type."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._counter: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append(
            {"method": request.method, "path": request.url.path, "json": body}
        )
        rtype = (body or {}).get("data", {}).get("type", "things")
        self._counter[rtype] = self._counter.get(rtype, 0) + 1
        return httpx.Response(
            200, json={"data": {"id": str(self._counter[rtype]), "type": rtype}}
        )


def _client(seek: _RecordingSeek) -> SeekClient:
    return SeekClient(
        "http://seek.test",
        auth=("admin", "pw"),
        http_client=httpx.Client(transport=httpx.MockTransport(seek.handler)),
    )


def test_create_investigation_posts_jsonapi_envelope():
    seek = _RecordingSeek()
    new_id = _client(seek).create_investigation(title="Inv", project_id="1")

    assert new_id == "1"
    req = seek.requests[-1]
    assert req["method"] == "POST"
    assert req["path"] == "/investigations"
    assert req["json"]["data"]["type"] == "investigations"
    assert req["json"]["data"]["attributes"]["title"] == "Inv"


def test_headers_use_jsonapi_media_type():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200, json={"data": {"id": "1", "type": "studies"}})

    client = SeekClient(
        "http://seek.test",
        token="tok",  # noqa: S106
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.create_study(title="S", investigation_id="1")

    assert captured["accept"] == "application/vnd.api+json"
    assert captured["content-type"] == "application/vnd.api+json"
    assert captured["authorization"] == "Bearer tok"


def test_default_project_id_reads_first_project():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "42", "type": "projects"}]})

    client = SeekClient(
        "http://seek.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.default_project_id() == "42"


def test_default_project_id_raises_without_projects():
    client = SeekClient(
        "http://seek.test",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(200, json={"data": []})
            )
        ),
    )
    with pytest.raises(ValueError, match="no projects"):
        client.default_project_id()


def test_push_minimal_experiment_threads_ids():
    from metaseed.seek.export import push_minimal_experiment

    seek = _RecordingSeek()
    # default_project_id -> GET /projects; sample_attribute_type_id -> GET
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/projects":
            return httpx.Response(200, json={"data": [{"id": "1", "type": "projects"}]})
        if request.method == "GET" and request.url.path == "/sample_attribute_types":
            return httpx.Response(
                200, json={"data": [{"id": "8", "attributes": {"title": "String"}}]}
            )
        return seek.handler(request)

    client = SeekClient(
        "http://seek.test",
        auth=("a", "b"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    ids = push_minimal_experiment(client)

    posted = [r["path"] for r in seek.requests if r["method"] == "POST"]
    assert posted == [
        "/investigations",
        "/studies",
        "/assays",
        "/sample_types",
        "/samples",
    ]
    # study links the investigation id that was returned first
    study_req = next(r for r in seek.requests if r["path"] == "/studies")
    assert (
        study_req["json"]["data"]["relationships"]["investigation"]["data"]["id"]
        == ids.investigation
    )
    assert ids.project == "1"
