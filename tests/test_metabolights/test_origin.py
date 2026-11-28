"""A MetaboLights import attaches the license the study names."""

from __future__ import annotations

import json

import httpx

from metaseed.metabolights import import_accession
from metaseed.metabolights.client import MetaboLightsClient
from metaseed.provenance import EBI_TERMS_OF_USE

from .test_import import FIXTURE


def _client(**study_fields: str) -> MetaboLightsClient:
    payload = json.loads(FIXTURE.read_text())
    payload["mtblsStudy"].update(study_fields)
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
    return MetaboLightsClient(http_client=httpx.Client(transport=transport))


def test_a_metabolights_import_records_where_it_came_from() -> None:
    origin = import_accession(
        "MTBLS1",
        client=_client(
            datasetLicense="CC0",
            datasetLicenseUrl="https://creativecommons.org/publicdomain/zero/1.0/",
        ),
    ).origin

    assert origin is not None
    assert origin.repository == "MetaboLights"
    assert origin.identifier == "MTBLS1"
    assert origin.record_url == "https://www.ebi.ac.uk/metabolights/MTBLS1"
    assert origin.license == "CC0-1.0"


def test_the_license_name_is_used_when_the_study_gives_no_url() -> None:
    origin = import_accession(
        "MTBLS1", client=_client(datasetLicense="EMBL-EBI Terms of Use")
    ).origin

    assert origin is not None
    assert origin.license == EBI_TERMS_OF_USE


def test_a_study_naming_no_license_falls_back_to_the_ebi_terms() -> None:
    # The recorded fixture predates the license fields and carries neither.
    origin = import_accession("MTBLS1", client=_client()).origin

    assert origin is not None
    assert origin.license == EBI_TERMS_OF_USE
