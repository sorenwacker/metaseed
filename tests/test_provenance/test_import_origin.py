"""An import origin survives the round trip a host stores it through."""

from __future__ import annotations

import datetime as dt
import json

from metaseed import MetaseedClient
from metaseed.provenance import ImportOrigin


def test_an_origin_round_trips_through_json() -> None:
    origin = ImportOrigin(
        repository="ENA",
        identifier="PRJEB1234",
        record_url="https://www.ebi.ac.uk/ena/browser/view/PRJEB1234",
        license="https://www.insdc.org/policy/",
        retrieved_at=dt.datetime(2026, 11, 28, 9, 30, tzinfo=dt.UTC),
    )

    stored = json.loads(json.dumps(origin.to_dict()))

    assert stored["retrieved_at"] == "2026-11-28T09:30:00+00:00"
    assert ImportOrigin.from_dict(stored) == origin


def test_a_dataset_built_without_an_import_has_no_origin() -> None:
    assert MetaseedClient("miappe", "1.2").origin is None
