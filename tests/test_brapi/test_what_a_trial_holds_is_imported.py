"""The import keeps what a trial's records state (#348).

Importing a FAIDARE trial dropped the study contacts and the units' treatments,
gave every observed variable only a name (so all of them failed MIAPPE's method
and scale rules), and placed germplasm shared by several studies in the first
of them only. Shapes follow FAIDARE's responses; names are placeholders.
"""

from __future__ import annotations

from typing import Any

from metaseed.brapi import import_brapi
from metaseed.brapi.mapper import build_dataset

_STUDIES = [
    {
        "studyDbId": "S1",
        "studyName": "Site one",
        "trialDbId": "T1",
        "trialName": "Network",
        "contacts": [
            {
                "contactDbId": "c1",
                "name": "Ada Example",
                "email": "ada@example.org",
                "instituteName": "Example Institute",
                "type": "Scientific contact",
                "orcid": "https://orcid.org/0000-0000-0000-0001",
            }
        ],
    },
    {"studyDbId": "S2", "studyName": "Site two", "trialDbId": "T1"},
]


def _entities(client) -> list[dict[str, Any]]:
    return client.serialize()["entities"]


def _of(client, entity_type: str) -> list[dict[str, Any]]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def test_a_study_s_contacts_become_its_persons() -> None:
    client = build_dataset(_STUDIES, [], [], [])

    (person,) = _of(client, "Person")
    assert person["name"] == "Ada Example"
    assert person["email"] == "ada@example.org"
    assert person["institution"] == "Example Institute"
    assert person["role"] == "Scientific contact"
    assert person["orcid"] == "https://orcid.org/0000-0000-0000-0001"
    assert person["study_id"] == "S1"


def test_germplasm_in_two_studies_is_in_both() -> None:
    germplasm = [
        {"germplasmDbId": "G1", "species": "Zea mays", "studyDbIds": ["S1", "S2"]}
    ]

    client = build_dataset(_STUDIES, [], [], germplasm)

    assert sorted(m["study_id"] for m in _of(client, "BiologicalMaterial")) == [
        "S1",
        "S2",
    ]


def test_a_unit_s_treatment_becomes_a_factor_and_its_value() -> None:
    units = [
        {
            "observationUnitDbId": f"ou-{n}",
            "studyDbId": "S1",
            "treatments": [{"factor": "water_regime", "modality": modality}],
        }
        for n, modality in ((1, "watered"), (2, "rainfed"))
    ]

    client = build_dataset(_STUDIES, units, [], [])

    (factor,) = _of(client, "Factor")
    assert factor["name"] == "water_regime"
    assert factor["study_id"] == "S1"
    values = sorted(v["value"] for v in _of(client, "FactorValue"))
    assert values == ["rainfed", "watered"]
    assert all(
        v["factor_id"] == factor["unique_id"] for v in _of(client, "FactorValue")
    )


_VARIABLE = {
    "observationVariableDbId": "V1",
    "observationVariableName": "Plant height",
    "trait": {
        "traitName": "Plant height",
        "traitDescription": "Height from soil to the top of the plant",
        "ontologyReference": {"ontologyName": "CO_322"},
        "traitDbId": "CO_322:0000018",
    },
    "method": {"methodName": "Ruler", "description": "Measured with a ruler"},
    "scale": {"scaleName": "cm", "dataType": "Numerical"},
}


def test_a_variable_keeps_its_trait_method_and_scale() -> None:
    client = build_dataset(
        _STUDIES, [], [], [], variables=[{**_VARIABLE, "studyDbIds": ["S1"]}]
    )

    (variable,) = _of(client, "ObservedVariable")
    assert variable["trait"] == "Plant height"
    assert variable["trait_description"] == "Height from soil to the top of the plant"
    assert variable["method"] == "Ruler"
    assert variable["method_description"] == "Measured with a ruler"
    assert variable["scale"] == "cm"
    assert variable["study_id"] == "S1"


class _Server:
    """A client double holding one study whose variables /variables lists."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def study(self, study_db_id: str) -> dict:
        return _STUDIES[0]

    def observation_units(self, study_db_id: str) -> list:
        return []

    def observations_for_study(self, study_db_id: str) -> list:
        return [
            {"observationVariableDbId": "V1", "observationVariableName": "Plant height"}
        ]

    def observations_for_unit(self, unit: str) -> list:
        return []

    def germplasm(self, study_db_id: str | None = None) -> list:
        return []

    def variables(self, study_db_id: str) -> list:
        self.asked.append(study_db_id)
        return [_VARIABLE]


def test_an_import_reads_each_study_s_variables() -> None:
    server = _Server()

    client = import_brapi(
        "https://server.example.org/brapi/v2/studies/S1", client=server
    )

    assert server.asked == ["S1"]
    (variable,) = _of(client, "ObservedVariable")
    assert variable["method"] == "Ruler"
