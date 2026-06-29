"""Conformance of the BrAPI export to the BrAPI v2 object structure.

Uses jsonschema to assert the v2 shape: every object carries its DbId, and an
observation unit nests its level inside observationUnitPosition (never a
top-level ``observationLevel`` — the bug fixed in this adapter). Opt-in (network).
"""

from __future__ import annotations

import pytest
from jsonschema import validate

from metaseed.brapi import import_brapi, to_brapi

BASE_URL = "https://test-server.brapi.org/brapi/v2"

_OU_SCHEMA = {
    "type": "object",
    "required": ["observationUnitDbId"],
    "not": {"required": ["observationLevel"]},  # must be nested, not top-level
    "properties": {
        "observationUnitPosition": {
            "type": "object",
            "properties": {"observationLevel": {"type": "object"}},
        }
    },
}
_REQUIRED_ID = {
    "studies": "studyDbId",
    "germplasm": "germplasmDbId",
    "observationUnits": "observationUnitDbId",
}


@pytest.mark.network
def test_brapi_export_matches_v2_shape():
    bodies = to_brapi(import_brapi(BASE_URL))
    for collection, id_field in _REQUIRED_ID.items():
        for obj in bodies.get(collection, []):
            assert id_field in obj, f"{collection} object missing {id_field}"
    for unit in bodies.get("observationUnits", []):
        validate(instance=unit, schema=_OU_SCHEMA)
