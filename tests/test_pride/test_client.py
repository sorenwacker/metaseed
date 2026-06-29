"""Tests for the PRIDE Archive client.

Request shapes and JSON parsing are checked hermetically with a mock transport.
A live smoke test against the real PRIDE API is marked ``network`` and skipped by
the default test run.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from metaseed.pride.client import PrideClient

FIXTURES = Path(__file__).parent / "fixtures"


def _mock(handler) -> PrideClient:
    return PrideClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_project_builds_the_request_and_parses_json():
    captured: dict[str, str] = {}
    payload = json.loads((FIXTURES / "project.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=payload)

    project = _mock(handler).project("PXD000001")

    assert project["accession"] == "PXD000001"
    assert captured["url"].endswith("/projects/PXD000001")
    assert "metaseed" in captured["user_agent"]  # EBI etiquette


def test_files_parses_a_plain_list():
    payload = json.loads((FIXTURES / "files.json").read_text())
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=payload)

    files = _mock(handler).files("PXD000001")

    assert len(files) == 3
    assert "/projects/PXD000001/files" in captured["url"]
    assert "page=0" in captured["url"]  # pagination params are sent
    assert files[0]["fileName"].endswith(".mztab.gz")


def test_files_follows_pagination_to_the_end():
    """A full 100-record page is followed by the next; a short page ends it.

    PRIDE caps /files at 100 records per page, so large datasets were truncated
    before this was paged through.
    """
    pages = [
        [{"fileName": f"f{i}.raw"} for i in range(100)],  # full page -> keep going
        [{"fileName": "last.raw"}],  # short page -> stop
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params).get("page", "0"))
        return httpx.Response(200, json=pages[page] if page < len(pages) else [])

    files = _mock(handler).files("PXD999999")

    assert len(files) == 101  # both pages collected, not just the first 100
    assert files[-1]["fileName"] == "last.raw"


def test_files_unwraps_the_hal_paged_shape():
    payload = json.loads((FIXTURES / "files.json").read_text())
    embedded = {"_embedded": {"files": payload}}
    client = _mock(lambda _r: httpx.Response(200, json=embedded))

    assert len(client.files("PXD000001")) == 3


def test_files_returns_empty_for_unexpected_payload():
    client = _mock(lambda _r: httpx.Response(200, json={"foo": "bar"}))
    assert client.files("PXD000001") == []


def test_project_returns_empty_for_non_object_payload():
    client = _mock(lambda _r: httpx.Response(200, json=[]))
    assert client.project("PXD000001") == {}


def test_raises_on_http_error():
    client = _mock(lambda _r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        client.project("PXD000001")


@pytest.mark.network
def test_project_live_smoke():
    """Hit the real PRIDE Archive API (opt-in: ``-m network``)."""
    client = PrideClient()
    project = client.project("PXD000001")
    assert isinstance(project, dict)
    assert project.get("accession") == "PXD000001"
    files = client.files("PXD000001")
    assert isinstance(files, list)
    if files:
        assert "fileName" in files[0]
