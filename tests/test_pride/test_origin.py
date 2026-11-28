"""A PRIDE import attaches the license the project names."""

from __future__ import annotations

import json

import httpx

from metaseed.pride import import_accession
from metaseed.pride.client import PrideClient
from metaseed.provenance import EBI_TERMS_OF_USE

from .test_import import FIXTURES, _mock_client


def _client_with_license(license_text: str | None) -> PrideClient:
    project = json.loads((FIXTURES / "project.json").read_text())
    if license_text is None:
        project.pop("license", None)
    else:
        project["license"] = license_text
    files = json.loads((FIXTURES / "files.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=files if request.url.path.endswith("/files") else project
        )

    return PrideClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_pride_import_records_where_it_came_from() -> None:
    origin = import_accession("PXD000001", client=_mock_client()).origin

    assert origin is not None
    assert origin.repository == "PRIDE"
    assert origin.identifier == "PXD000001"
    assert origin.record_url == "https://www.ebi.ac.uk/pride/archive/projects/PXD000001"
    # The fixture's project says "EBI terms of use", as older PRIDE projects do.
    assert origin.license == EBI_TERMS_OF_USE


def test_a_cc0_project_is_imported_under_cc0() -> None:
    client = import_accession(
        "PXD000001", client=_client_with_license("Creative Commons Public Domain (CC0)")
    )

    assert client.origin is not None
    assert client.origin.license == "CC0-1.0"


def test_a_project_naming_no_license_falls_back_to_the_ebi_terms() -> None:
    client = import_accession("PXD000001", client=_client_with_license(None))

    assert client.origin is not None
    assert client.origin.license == EBI_TERMS_OF_USE
