"""Tests for the BrAPI -> miappe-profile mapper (pure, no network)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from metaseed.brapi.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "brapi.json"


def _payloads():
    return json.loads(FIXTURE.read_text())


def _build():
    payloads = _payloads()
    return build_dataset(
        payloads["studies"]["result"]["data"],
        payloads["observationunits"]["result"]["data"],
        payloads["observations"]["result"]["data"],
        payloads["germplasm"]["result"]["data"],
    )


def _entities(client) -> list[dict]:
    return client.serialize()["entities"]


def _by_type(client, entity_type: str) -> list[dict]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def test_build_dataset_creates_the_full_hierarchy():
    client = _build()

    counts = Counter(e["_type"] for e in _entities(client))
    assert counts["Investigation"] == 1  # both studies share trial T01
    assert counts["Study"] == 2
    assert counts["BiologicalMaterial"] == 2
    assert counts["ObservationUnit"] == 2
    assert counts["ObservedVariable"] == 2  # VAR_HEIGHT deduped across 2 obs
    assert counts["DataFile"] == 1


def test_ids_and_references_are_mapped():
    client = _build()

    study = {s["unique_id"]: s for s in _by_type(client, "Study")}
    assert study["1001"]["investigation_id"] == "T01"
    assert study["1001"]["experimental_site_name"] == "Wageningen field A"

    units = {u["unique_id"]: u for u in _by_type(client, "ObservationUnit")}
    assert units["OU1"]["study_id"] == "1001"
    assert units["OU1"]["biological_material_id"] == "G1"
    # The level (nested in observationUnitPosition in BrAPI v2) and the
    # block/replicate relationships are captured, not dropped.
    assert units["OU1"]["observation_level"] == "plot"
    assert units["OU1"]["observation_level_code"] == "1"
    assert units["OU1"]["observation_unit_block"] == "1"
    assert units["OU1"]["observation_unit_replicate"] == "1"

    germplasm = {g["unique_id"]: g for g in _by_type(client, "BiologicalMaterial")}
    assert germplasm["G1"]["genus"] == "Zea"
    assert germplasm["G1"]["accession_number"] == "PI 550473"
    assert germplasm["G1"]["study_id"] == "1001"


def test_data_files_reference_urls_not_downloads():
    client = _build()

    files = _by_type(client, "DataFile")
    assert len(files) == 1
    assert files[0]["link"] == "https://example.org/files/1001/phenotypes.csv"
    assert files[0]["study_id"] == "1001"


def test_empty_inputs_yield_empty_dataset():
    client = build_dataset([], [], [], [])
    assert client.serialize()["entities"] == []
