"""A BrAPI address names what to import: the server, one trial, or one study.

Given a trial's address, the importer appended ``/studies`` to it; FAIDARE
ignored the trial and answered with its 2763 studies, and the import fetched
them all, and then each study's observation units, for hours.
"""

from __future__ import annotations

import json
from urllib.parse import unquote

import httpx
import pytest

from metaseed.brapi import BrapiAddress, import_brapi, parse_address
from metaseed.brapi.client import BrapiClient

BASE = "https://server.example.org/brapi/v2"
TRIAL = "dXJuOnRyaWFsLzQy%3D"


def _study(study_id: str, trial_id: str = "T1") -> dict:
    return {
        "studyDbId": study_id,
        "studyName": f"Study {study_id}",
        "trialDbId": trial_id,
        "trialName": "Network",
    }


def _page(data: list) -> dict:
    return {"metadata": {"pagination": {"totalPages": 1}}, "result": {"data": data}}


class _Server:
    """Three studies, two in trial T1; germplasm per study and for the server."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/brapi/v2/")
        self.asked.append(f"{path}?{request.url.query.decode()}".rstrip("?"))
        study = request.url.params.get("studyDbId")
        # The identifier reaches the server percent-decoded.
        answers = {
            f"trials/{unquote(TRIAL)}": {
                "result": {
                    "trialDbId": TRIAL,
                    "trialName": "Network",
                    "studies": [{"studyDbId": "S1"}, {"studyDbId": "S2"}],
                }
            },
            "studies": _page([_study("S1"), _study("S2"), _study("S3", "T2")]),
            "studies/S1": {"result": _study("S1")},
            "studies/S2": {"result": _study("S2")},
            "studies/S3": {"result": _study("S3", "T2")},
            "observationunits": _page([]),
            "germplasm": _page(
                [{"germplasmDbId": f"G-{study}", "germplasmName": study}]
                if study
                else [
                    {"germplasmDbId": f"G-{s}", "germplasmName": s}
                    for s in ("S1", "S2", "S3")
                ]
            ),
        }
        if path not in answers:
            return httpx.Response(404, json={"errors": [{"message": "no such path"}]})
        return httpx.Response(200, json=answers[path])


@pytest.fixture
def server() -> _Server:
    return _Server()


def _client(server: _Server) -> BrapiClient:
    return BrapiClient(
        BASE, http_client=httpx.Client(transport=httpx.MockTransport(server))
    )


def _studies(client) -> list[str]:
    return sorted(
        entity["unique_id"]
        for entity in client.serialize()["entities"]
        if entity["_type"] == "Study"
    )


def _materials(client) -> list[str]:
    return sorted(
        entity["unique_id"]
        for entity in client.serialize()["entities"]
        if entity["_type"] == "BiologicalMaterial"
    )


class TestReadingTheAddress:
    def test_the_base_url_names_the_server(self) -> None:
        assert parse_address(f"{BASE}/") == BrapiAddress(BASE)

    def test_a_trial_s_address_names_the_trial_as_the_server_spells_it(self) -> None:
        assert parse_address(f"{BASE}/trials/{TRIAL}") == BrapiAddress(
            BASE, trial_db_id=TRIAL
        )
        assert parse_address(f"{BASE}/trials/42/") == BrapiAddress(
            BASE, trial_db_id="42"
        )

    def test_a_study_s_address_names_the_study(self) -> None:
        assert parse_address(f"{BASE}/studies/S1") == BrapiAddress(
            BASE, study_db_id="S1"
        )

    @pytest.mark.parametrize(
        "address",
        [f"{BASE}/studies", f"{BASE}/germplasm/G1", f"{BASE}/trials/42/studies"],
    )
    def test_any_other_resource_is_refused_naming_the_three_forms(
        self, address: str
    ) -> None:
        with pytest.raises(ValueError, match="base URL") as refused:
            parse_address(address)

        assert f"({BASE})" in str(refused.value)
        assert f"{BASE}/trials/<trialDbId>" in str(refused.value)


class TestWhatIsImported:
    def test_a_trial_s_address_imports_its_studies_and_their_germplasm(
        self, server
    ) -> None:
        client = import_brapi(f"{BASE}/trials/{TRIAL}", client=_client(server))

        assert _studies(client) == ["S1", "S2"]
        assert _materials(client) == ["G-S1", "G-S2"]
        assert "studies?page=0" not in server.asked, (
            "the server's study list was not read"
        )
        assert "germplasm?page=0" not in server.asked, (
            "the server's germplasm was not read"
        )
        assert "germplasm?studyDbId=S1&page=0" in server.asked

    def test_a_study_s_address_imports_that_study(self, server) -> None:
        client = import_brapi(f"{BASE}/studies/S3", client=_client(server))

        assert _studies(client) == ["S3"]
        assert _materials(client) == ["G-S3"]

    def test_the_base_url_still_imports_every_study(self, server) -> None:
        client = import_brapi(BASE, client=_client(server))

        assert _studies(client) == ["S1", "S2", "S3"]
        assert _materials(client) == ["G-S1", "G-S2", "G-S3"]

    def test_a_refused_address_asks_the_server_nothing(self, server) -> None:
        with pytest.raises(ValueError):
            import_brapi(f"{BASE}/germplasm/G1", client=_client(server))

        assert server.asked == []

    def test_germplasm_two_studies_share_is_one_material(self, server) -> None:
        shared = {"germplasmDbId": "G-shared", "germplasmName": "shared"}
        original = server.__call__

        def sharing(request: httpx.Request) -> httpx.Response:
            response = original(request)
            if request.url.path.endswith("/germplasm"):
                body = json.loads(response.content)
                body["result"]["data"].append(shared)
                return httpx.Response(200, json=body)
            return response

        client = import_brapi(
            f"{BASE}/trials/{TRIAL}",
            client=BrapiClient(
                BASE, http_client=httpx.Client(transport=httpx.MockTransport(sharing))
            ),
        )

        assert _materials(client) == ["G-S1", "G-S2", "G-shared"]
