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
            "observationunits": _page(
                [{"observationUnitDbId": f"U-{study}", "studyDbId": study}]
                if study
                else []
            ),
            "observations": _page(
                [{"observationDbId": f"O-{study}", "observationUnitDbId": f"U-{study}"}]
                if study
                else []
            ),
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
        assert any(asked.startswith("germplasm?studyDbId=S1") for asked in server.asked)

    def test_observations_come_per_study_where_the_server_filters_them(
        self, server
    ) -> None:
        """One request for the study, not one per observation unit."""
        import_brapi(f"{BASE}/studies/S1", client=_client(server))

        assert any(
            asked.startswith("observations?studyDbId=S1") for asked in server.asked
        )
        assert not any("observationUnitDbId=" in asked for asked in server.asked)

    def test_pages_are_asked_for_a_thousand_at_a_time(self, server) -> None:
        import_brapi(f"{BASE}/studies/S1", client=_client(server))

        assert all(
            "pageSize=1000" in asked for asked in server.asked if "page=" in asked
        )

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


def test_a_study_too_deep_for_the_server_s_filter_is_read_per_unit() -> None:
    """FAIDARE answers 500 past the 20,000th observation of a study; the
    import then asks each observation unit, which never reaches that deep."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/brapi/v2/")
        asked.append(f"{path}?{request.url.query.decode()}")
        if path == "studies/S1":
            return httpx.Response(200, json={"result": _study("S1")})
        if path == "observationunits":
            return httpx.Response(
                200,
                json=_page(
                    [
                        {"observationUnitDbId": f"U{n}", "studyDbId": "S1"}
                        for n in range(3)
                    ]
                ),
            )
        if path == "observations" and request.url.params.get("studyDbId"):
            if request.url.params.get("page") == "0":
                return httpx.Response(
                    200,
                    json={
                        "metadata": {"pagination": {"totalPages": 30}},
                        "result": {
                            "data": [
                                {
                                    "observationDbId": "lost-if-kept",
                                    "observationVariableDbId": "V-partial",
                                }
                            ]
                        },
                    },
                )
            return httpx.Response(500, json={"errors": [{"message": "window"}]})
        if path == "observations":
            unit = request.url.params["observationUnitDbId"]
            return httpx.Response(
                200,
                json=_page(
                    [
                        {
                            "observationDbId": f"O-{unit}",
                            "observationVariableDbId": f"V-{unit}",
                        }
                    ]
                ),
            )
        if path == "germplasm":
            return httpx.Response(200, json=_page([]))
        return httpx.Response(404, json={})

    client = import_brapi(
        f"{BASE}/studies/S1",
        client=BrapiClient(
            BASE, http_client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )

    variables = [
        e for e in client.serialize()["entities"] if e["_type"] == "ObservedVariable"
    ]
    assert sorted(v["unique_id"] for v in variables) == ["V-U0", "V-U1", "V-U2"], (
        "every unit's observation, none of the partial page"
    )
    assert sum("observationUnitDbId=" in a for a in asked) == 3
