"""A BrAPI import attaches a license only when every imported study names the same one."""

from __future__ import annotations

import json

import httpx

from metaseed.brapi import import_brapi
from metaseed.brapi.client import BrapiClient

from .test_import import BASE_URL, FIXTURE


def _client(*licenses: str | None) -> BrapiClient:
    payloads = json.loads(FIXTURE.read_text())
    for study, license_text in zip(
        payloads["studies"]["result"]["data"], licenses, strict=True
    ):
        study["license"] = license_text

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads[request.url.path.rsplit("/", 1)[-1]])

    return BrapiClient(
        BASE_URL, http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_a_brapi_import_records_where_it_came_from() -> None:
    url = "https://creativecommons.org/licenses/by/4.0"
    origin = import_brapi(BASE_URL, client=_client(url, url)).origin

    assert origin is not None
    assert origin.repository == "BrAPI"
    assert origin.identifier == BASE_URL
    assert origin.record_url == BASE_URL
    assert origin.license == "CC-BY-4.0"


def test_studies_that_disagree_attach_no_license() -> None:
    origin = import_brapi(
        BASE_URL,
        client=_client("https://creativecommons.org/licenses/by/4.0", "CC0-1.0"),
    ).origin

    assert origin is not None
    assert origin.license is None


def test_a_study_naming_no_license_leaves_the_import_without_one() -> None:
    origin = import_brapi(
        BASE_URL, client=_client("https://creativecommons.org/licenses/by/4.0", None)
    ).origin

    assert origin is not None
    assert origin.license is None
