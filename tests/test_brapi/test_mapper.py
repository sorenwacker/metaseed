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
    assert study["1001"]["experimental_site_name"] == "Example field A"

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


def test_faidare_s_level_strings_are_read_as_block_replicate_and_plot() -> None:
    """FAIDARE lists a unit's level relationships as one string per unit and
    puts the level's number where BrAPI puts its name; the import crashed on
    the string. Shape copied from a Drops Phenotyping Network unit."""
    from metaseed.brapi.mapper import build_dataset

    unit = {
        "observationUnitDbId": "ou-223977",
        "studyDbId": "S1",
        "observationUnitPosition": {
            "observationLevel": {
                "levelName": "223977",
                "levelOrder": "REPLICATE>BLOCK>PLOT",
            },
            "observationLevelRelationships": [
                "REPLICATE>BLOCK>PLOT:223977,REPLICATE>BLOCK:5,REPLICATE:2"
            ],
            "positionCoordinateX": "10",
            "positionCoordinateXType": "X",
        },
    }

    client = build_dataset([{"studyDbId": "S1", "studyName": "S"}], [unit], [], [])

    (ou,) = [
        e for e in client.serialize()["entities"] if e["_type"] == "ObservationUnit"
    ]
    assert ou["observation_level"] == "plot"
    assert ou["observation_level_code"] == "223977"
    assert ou["observation_unit_block"] == "5"
    assert ou["observation_unit_replicate"] == "2"


def test_the_server_s_spelling_becomes_miappe_s_vocabulary() -> None:
    """Breedbase sends TEST, FAIDARE a list of CO_715 descriptions; MIAPPE's
    rules know test and field. What cannot be placed is kept as sent (#353)."""
    from metaseed.brapi.mapper import build_dataset

    study = {
        "studyDbId": "S1",
        "studyName": "S",
        "growthFacility": {"description": "field environment condition, greenhouse"},
    }
    units = [
        {
            "observationUnitDbId": f"ou-{n}",
            "studyDbId": "S1",
            "observationUnitPosition": {"entryType": entry},
        }
        for n, entry in enumerate(("TEST", "Check", "border row"))
    ]

    client = build_dataset([study], units, [], [])

    entities = client.serialize()["entities"]
    (s,) = [e for e in entities if e["_type"] == "Study"]
    assert s["growth_facility_type"] == "field"
    assert [e["entry_type"] for e in entities if e["_type"] == "ObservationUnit"] == [
        "test",
        "check",
        "border row",
    ]


def test_a_server_s_own_key_is_a_valid_miappe_identifier() -> None:
    """FAIDARE's DbIds are base64 and end in '='; a file's name has a dot. The
    profiles refused both, and the reload then dropped the entity (#353)."""
    from metaseed import ProfileFacade

    for version in ("1.1", "1.2"):
        facade = ProfileFacade("miappe", version)
        study = facade.Study.create(
            unique_id="dXJuOklOUkFFLVVSR0kvc3R1ZHkvQ2FtMTE=",
            title="Cam11",
            investigation_id="T",
        )
        assert study.unique_id.endswith("=")
        file = facade.DataFile.create(
            unique_id="image-archive.zip",
            study_id="S",
            name="images",
            link="https://x.example.org/a",
        )
        assert file.unique_id == "image-archive.zip"


def test_the_documented_example_reloads_whole() -> None:
    """The issue's own reproduction: ten entities imported, ten after a reload,
    every child with its parent (#353). The shapes are the reference server's
    for study1, reduced to what matters."""
    from metaseed import MetaseedClient
    from metaseed.brapi.mapper import build_dataset

    study = {
        "studyDbId": "study1",
        "studyName": "Study 1",
        "trialDbId": "trial1",
        "trialName": "Trial 1",
        "growthFacility": {"description": "field environment condition, greenhouse"},
        "dataLinks": [
            {
                "url": "https://server.example.org/files/image-archive.zip",
                "name": "images",
            }
        ],
    }
    units = [
        {
            "observationUnitDbId": f"unit{n}",
            "studyDbId": "study1",
            "germplasmDbId": f"germ{n}",
            "observationUnitPosition": {"entryType": "TEST"},
        }
        for n in range(3)
    ]
    germplasm = [
        {"germplasmDbId": f"germ{n}", "germplasmName": f"G{n}"} for n in range(3)
    ]
    observations = [
        {
            "observationDbId": "o1",
            "observationVariableDbId": "var1",
            "studyDbId": "study1",
        }
    ]
    data = build_dataset([study], units, observations, germplasm).serialize()
    assert len(data["entities"]) == 10

    reloaded = MetaseedClient(data["profile"], data["version"])
    reloaded.load(data)

    after = reloaded.serialize()["entities"]
    assert len(after) == 10
    assert all(
        e.get("_parent_unique_id") for e in after if e["_type"] != "Investigation"
    )
