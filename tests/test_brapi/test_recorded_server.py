"""Import against responses recorded from the BrAPI reference server.

The hand-written fixture answers every request with the same canned payload, so
it proves the mapper is self-consistent but not that it matches a real server.
These tests replay ``fixtures/brapi_v2_recorded.json``, which stores the exact
``(endpoint, params) -> response`` pairs ``test-server.brapi.org`` returned, and
answers an unrecorded query the way the server did: with nothing.

That distinction is the point. The reference server does not honour a
``studyDbId`` filter on ``/observations`` even though its observation records
carry one, so an importer that asks that way silently imports no measurements at
all -- which the canned fixture cannot show.

Re-record with ``uv run python scripts/record_brapi_fixture.py``; person-shaped values are
replaced on the way in, so no real identities live here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from metaseed.brapi import import_brapi
from metaseed.brapi.client import BrapiClient

FIXTURE = Path(__file__).parent / "fixtures" / "brapi_v2_recorded.json"
BASE_URL = "https://test-server.brapi.org/brapi/v2"

_EMPTY: dict[str, Any] = {
    "metadata": {"pagination": {"currentPage": 0, "totalCount": 0, "totalPages": 1}},
    "result": {"data": []},
}


def _recorded_client() -> BrapiClient:
    """A client replaying the recording, and answering anything else as the
    server did: with an empty page rather than a canned payload."""
    records = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        params = {
            key: value
            for key, value in request.url.params.items()
            if key not in {"pageSize", "page"}
        }
        for record in records:
            if record["endpoint"] == endpoint and record["params"] == params:
                return httpx.Response(200, json=record["response"])
        return httpx.Response(200, json=_EMPTY)

    transport = httpx.MockTransport(handler)
    return BrapiClient(BASE_URL, http_client=httpx.Client(transport=transport))


def _entities(client: Any) -> list[dict[str, Any]]:
    return list(client.serialize()["entities"])


def test_the_studies_a_real_server_returns_are_imported() -> None:
    client = import_brapi(BASE_URL, client=_recorded_client())

    studies = [e for e in _entities(client) if e.get("_type") == "Study"]
    assert len(studies) == 3, "every study the server listed must be imported"


def test_observation_units_are_imported_from_the_recorded_shape() -> None:
    client = import_brapi(BASE_URL, client=_recorded_client())

    units = [e for e in _entities(client) if e.get("_type") == "ObservationUnit"]
    assert len(units) == 3


def test_measurements_are_imported_rather_than_silently_dropped() -> None:
    """The recording holds four observations, reachable only by observation unit.

    An importer that asks ``/observations?studyDbId=…`` gets nothing from the
    reference server, so this is the assertion that separates "the mapper works"
    from "an import of a real server produces data".
    """
    client = import_brapi(BASE_URL, client=_recorded_client())

    variables = [e for e in _entities(client) if e.get("_type") == "ObservedVariable"]
    assert variables, (
        "no measurements were imported; the observations the server holds were not fetched"
    )


def test_germplasm_becomes_biological_material() -> None:
    client = import_brapi(BASE_URL, client=_recorded_client())

    materials = [e for e in _entities(client) if e.get("_type") == "BiologicalMaterial"]
    assert len(materials) == 3


def test_a_measurement_is_not_imported_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collecting per unit must not duplicate an observation a server returns
    under more than one unit."""
    client = _recorded_client()
    original = client.observations_for_unit

    def every_unit_returns_the_same(_unit_id: str) -> list[dict[str, Any]]:
        return original("observation_unit1")

    monkeypatch.setattr(client, "observations_for_unit", every_unit_returns_the_same)
    imported = import_brapi(BASE_URL, client=client)

    units = [e for e in _entities(imported) if e.get("_type") == "ObservationUnit"]
    variables = [e for e in _entities(imported) if e.get("_type") == "ObservedVariable"]
    assert len(units) == 3
    assert len(variables) <= 2, "the same observation was imported once per unit"


def test_the_export_still_matches_the_brapi_v2_shape() -> None:
    """Conformance without the network, so CI covers it.

    The equivalent check in ``test_conformance.py`` is ``network``-marked and
    therefore never runs in CI; replaying the recording gives the same guarantee
    against the same server's data.
    """
    from jsonschema import validate

    from metaseed.brapi import to_brapi

    bodies = to_brapi(import_brapi(BASE_URL, client=_recorded_client()))

    for collection, id_field in (
        ("studies", "studyDbId"),
        ("germplasm", "germplasmDbId"),
        ("observationUnits", "observationUnitDbId"),
    ):
        for obj in bodies.get(collection, []):
            assert id_field in obj, f"{collection} object missing {id_field}"
    for unit in bodies.get("observationUnits", []):
        validate(
            instance=unit,
            schema={
                "type": "object",
                "required": ["observationUnitDbId"],
                # The level belongs inside observationUnitPosition, never at the
                # top level -- the bug this adapter fixed.
                "not": {"required": ["observationLevel"]},
            },
        )


@pytest.mark.parametrize("forbidden", ["@brapi.org", "Dave Breeder", "0000-0002"])
def test_the_fixture_carries_no_real_identities(forbidden: str) -> None:
    """Recorded from a public server, so it is de-identified on the way in."""
    assert forbidden not in FIXTURE.read_text()
