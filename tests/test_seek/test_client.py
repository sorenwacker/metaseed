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


def test_create_controlled_vocab_posts_terms():
    seek = _RecordingSeek()
    new_id = _client(seek).create_controlled_vocab(
        title="Organism",
        terms=[{"label": "human", "iri": "x", "parent_iri": None}],
        source_ontology="ncbitaxon",
    )
    assert new_id == "1"
    req = seek.requests[-1]
    assert req["method"] == "POST"
    assert req["path"] == "/sample_controlled_vocabs"
    attrs = req["json"]["data"]["attributes"]
    assert attrs["title"] == "Organism"
    assert attrs["sample_controlled_vocab_terms_attributes"][0]["label"] == "human"


def test_find_sample_type_id_by_title_scopes_by_project():
    # SEEK's /sample_types LIST omits the projects relationship; the project is
    # confirmed against the single-resource detail view.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sample_types":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "10", "attributes": {"title": "Sample"}},
                        {"id": "20", "attributes": {"title": "Sample"}},
                    ]
                },
            )
        proj = {"10": "1", "20": "2"}[request.url.path.rsplit("/", 1)[1]]
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": request.url.path.rsplit("/", 1)[1],
                    "attributes": {"title": "Sample"},
                    "relationships": {
                        "projects": {"data": [{"id": proj, "type": "projects"}]}
                    },
                }
            },
        )

    client = SeekClient(
        "http://seek.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.find_sample_type_id_by_title("Sample", project_id="2") == "20"
    assert client.find_sample_type_id_by_title("Sample", project_id="9") is None
    assert client.find_sample_type_id_by_title("Missing", project_id="1") is None
    # with no project filter, the first title match wins (no detail fetch needed)
    assert client.find_sample_type_id_by_title("Sample") == "10"


def test_find_controlled_vocab_id_by_title():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "5", "attributes": {"title": "Organism"}}]},
        )

    client = SeekClient(
        "http://seek.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.find_controlled_vocab_id_by_title("Organism") == "5"
    assert client.find_controlled_vocab_id_by_title("Nope") is None


def test_list_projects_returns_id_title_pairs():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "1", "attributes": {"title": "Alpha"}},
                    {"id": "2", "attributes": {"title": "Beta"}},
                ]
            },
        )

    client = SeekClient(
        "http://seek.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.list_projects() == [("1", "Alpha"), ("2", "Beta")]


def test_client_from_settings_uses_url_and_token():
    from metaseed.seek.client import client_from_settings

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200, json={"data": [{"id": "1", "type": "projects"}]})

    client = client_from_settings(
        {"url": "http://seek.test", "api_key": "tok"},
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.default_project_id()
    assert captured["authorization"] == "Bearer tok"


def test_client_from_settings_blank_key_is_unauthenticated():
    from metaseed.seek.client import client_from_settings

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200, json={"data": [{"id": "1", "type": "projects"}]})

    client = client_from_settings(
        {"url": "http://seek.test", "api_key": ""},
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.default_project_id()
    assert "authorization" not in captured


def test_client_from_settings_requires_url():
    from metaseed.seek.client import client_from_settings

    with pytest.raises(ValueError, match="SEEK URL"):
        client_from_settings({"api_key": "tok"})
