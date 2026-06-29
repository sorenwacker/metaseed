"""Tests for the BrAPI exporter (miappe dataset -> BrAPI v2 JSON)."""

from __future__ import annotations

import json
from pathlib import Path

from metaseed.brapi import to_brapi
from metaseed.brapi.mapper import build_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "brapi.json"


def _payloads() -> dict:
    return json.loads(FIXTURE.read_text())


def _build():
    payloads = _payloads()
    return build_dataset(
        payloads["studies"]["result"]["data"],
        payloads["observationunits"]["result"]["data"],
        payloads["observations"]["result"]["data"],
        payloads["germplasm"]["result"]["data"],
    )


def test_export_emits_the_expected_collections():
    objects = to_brapi(_build())

    assert set(objects) == {"trials", "studies", "observationUnits", "germplasm"}
    assert len(objects["trials"]) == 1  # both studies share trial T01
    assert len(objects["studies"]) == 2
    assert len(objects["observationUnits"]) == 2
    assert len(objects["germplasm"]) == 2


def test_trials_and_studies_carry_their_ids_and_names():
    objects = to_brapi(_build())

    trial = objects["trials"][0]
    assert trial["trialDbId"] == "T01"
    assert trial["trialName"] == "Maize drought programme"

    studies = {s["studyDbId"]: s for s in objects["studies"]}
    assert studies["1001"]["studyName"] == "Drought trial 2024"
    assert studies["1001"]["trialDbId"] == "T01"
    assert studies["1001"]["locationName"] == "Wageningen field A"


def test_germplasm_carries_taxonomy_and_study_links():
    germplasm = {g["germplasmDbId"]: g for g in to_brapi(_build())["germplasm"]}

    assert germplasm["G1"]["germplasmName"] == "B73"
    assert germplasm["G1"]["genus"] == "Zea"
    assert germplasm["G1"]["species"] == "Zea mays"
    assert germplasm["G1"]["accessionNumber"] == "PI 550473"
    assert germplasm["G1"]["studyDbIds"] == ["1001"]


def test_observation_units_link_to_study_and_germplasm():
    units = {
        u["observationUnitDbId"]: u for u in to_brapi(_build())["observationUnits"]
    }

    assert units["OU1"]["studyDbId"] == "1001"
    assert units["OU1"]["germplasmDbId"] == "G1"
    assert units["OU1"]["observationUnitPosition"]["replicate"] == "1"


def test_empty_inputs_yield_no_collections():
    assert to_brapi(build_dataset([], [], [], [])) == {}


def test_roundtrip_preserves_key_ids():
    # import (mapper) -> export must preserve trial/study/germplasm ids
    objects = to_brapi(_build())

    assert {t["trialDbId"] for t in objects["trials"]} == {"T01"}
    assert {s["studyDbId"] for s in objects["studies"]} == {"1001", "1002"}
    assert {g["germplasmDbId"] for g in objects["germplasm"]} == {"G1", "G2"}
