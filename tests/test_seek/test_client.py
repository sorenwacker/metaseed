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

from metaseed.seek.client import SeekApiError, SeekClient


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


class _RecordingIsaForms:
    """A mock SEEK for the form-encoded ISA endpoints.

    They answer a successful create with a 302 whose Location carries the new
    record's id, and a rejected one with a 422 of HTML — neither is JSON:API.
    """

    def __init__(self, status: int = 302, item_id: str = "42") -> None:
        self.requests: list[dict[str, Any]] = []
        self._status = status
        self._item_id = item_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(
            {
                "path": request.url.path,
                "content_type": request.headers.get("Content-Type"),
                "accept": request.headers.get("Accept"),
                "body": request.content.decode(),
            }
        )
        if request.url.path == "/isa_tags":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "5", "attributes": {"title": "protocol"}},
                        {"id": "11", "attributes": {"title": "input"}},
                    ]
                },
            )
        if self._status == 302:
            return httpx.Response(
                302,
                headers={
                    "Location": (
                        f"http://seek.test/single_pages/4?item_id={self._item_id}"
                        "&item_type=assay"
                    )
                },
            )
        return httpx.Response(self._status, text="<html>rejected</html>")


def _form_client(seek: _RecordingIsaForms) -> SeekClient:
    return SeekClient(
        "http://seek.test",
        token="t",  # noqa: S106
        http_client=httpx.Client(transport=httpx.MockTransport(seek.handler)),
    )


class TestIsaFormEndpoints:
    def test_isa_tag_ids_resolves_titles_to_ids(self):
        seek = _RecordingIsaForms()
        assert _form_client(seek).isa_tag_ids() == {"protocol": "5", "input": "11"}

    def test_a_form_post_is_not_sent_as_jsonapi(self):
        # The JSON branch of these controllers is unreachable: check_json_id_type
        # demands a JSON:API `data` member, then convert_json_params drops the
        # isa_* key. Sending JSON gets a 422/500 whatever the body.
        seek = _RecordingIsaForms()
        _form_client(seek).create_isa_assay(title="A", study_id="3", assay_class_id=3)
        sent = seek.requests[-1]
        assert sent["content_type"] == "application/x-www-form-urlencoded"
        assert "application/json" not in (sent["accept"] or "")
        assert "isa_assay%5Bassay%5D%5Btitle%5D=A" in sent["body"]

    def test_the_created_id_comes_from_the_redirect(self):
        seek = _RecordingIsaForms(item_id="89")
        assert (
            _form_client(seek).create_isa_assay(
                title="A", study_id="3", assay_class_id=3
            )
            == "89"
        )

    def test_a_rejected_form_post_raises_rather_than_returning_none(self):
        # A 422 renders the form again as HTML. Returning None would let the sync
        # carry on and attach samples to an assay that was never created.
        seek = _RecordingIsaForms(status=422)
        with pytest.raises(SeekApiError):
            _form_client(seek).create_isa_assay(
                title="A", study_id="3", assay_class_id=3
            )

    def test_isa_study_posts_both_sample_types(self):
        seek = _RecordingIsaForms()
        _form_client(seek).create_isa_study(
            title="S",
            investigation_id="1",
            source_title="Src",
            source_attributes=[],
            collection_title="Coll",
            collection_attributes=[],
        )
        sent = seek.requests[-1]
        assert sent["path"] == "/isa_studies"
        assert "source_sample_type" in sent["body"]
        assert "sample_collection_sample_type" in sent["body"]

    def test_study_sample_types_are_keyed_by_title_not_position(self):
        # GET /studies/{id}/sample_types does not preserve study.sample_types
        # order, so Source cannot be identified as "the first one".
        class _Types(_RecordingIsaForms):
            def handler(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": "101", "attributes": {"title": "Coll"}},
                            {"id": "100", "attributes": {"title": "Src"}},
                        ]
                    },
                )

        assert _form_client(_Types()).study_sample_type_ids("7") == {
            "Coll": "101",
            "Src": "100",
        }


def test_seek_client_satisfies_the_isa_writer_port():
    """The port is only worth having if the real client actually implements it.

    Without this the protocol could drift from ``SeekClient`` unnoticed, and the
    sync would type-check against an interface nothing provides.
    """
    from metaseed.seek.ports import IsaWriter

    writer: IsaWriter = SeekClient("http://seek.test", token="t")  # noqa: S106
    assert writer is not None


def test_every_send_path_carries_the_api_token():
    # ``_send`` is the one place requests leave the client; a caller reaching an
    # endpoint through it directly (the ISA-JSON export check does) must still
    # be authenticated, or SEEK silently serves the anonymous view — which
    # drops every assay whose samples the public cannot see, with no error.
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"data": []})

    client = SeekClient(
        "http://seek.test",
        token="sekrit",  # noqa: S106 — a fake for the mock transport, not a secret
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client._send(
        "GET", "/investigations/1/export_isa", headers={"Accept": "application/json"}
    )
    assert seen == ["Bearer sekrit"]
