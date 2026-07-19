"""Export a ``miappe``-profile dataset to BrAPI v2 JSON objects.

Produces the BrAPI v2 request bodies a BrAPI server accepts (``trials``,
``studies``, ``observationUnits``, ``germplasm``) from a metaseed dataset bound
to the ``miappe`` profile. Pure and dependency-free (stdlib only); it never
contacts a server. Data files are *referenced* via study ``dataLinks``, never
uploaded.

This is the round-trip partner of :func:`metaseed.brapi.build_dataset`: it
inverts the mapper, turning Investigations back into trials, Studies into
studies, ObservationUnits into observation units, and BiologicalMaterials into
germplasm. Entity ``unique_id`` values become the corresponding BrAPI ``DbId``,
so parent references survive the round trip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed._mapping import clean as _clean

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


def _trial(investigation: dict[str, Any]) -> dict[str, Any]:
    """Build a BrAPI ``trial`` from a miappe Investigation."""
    trial_id = investigation.get("unique_id")
    return _clean(
        {
            "trialDbId": trial_id,
            "trialName": investigation.get("title") or trial_id,
            "trialDescription": investigation.get("description"),
        }
    )


def _study(study: dict[str, Any]) -> dict[str, Any]:
    """Build a BrAPI ``study`` from a miappe Study."""
    study_id = study.get("unique_id")
    design = _clean(
        {
            "PUI": study.get("experimental_design_type"),
            "description": study.get("experimental_design_description"),
        }
    )
    facility = _clean({"description": study.get("growth_facility_type")})
    return _clean(
        {
            "studyDbId": study_id,
            "studyName": study.get("title") or study_id,
            "trialDbId": study.get("investigation_id"),
            "studyDescription": study.get("description"),
            "startDate": study.get("start_date"),
            "endDate": study.get("end_date"),
            "locationName": study.get("experimental_site_name"),
            "experimentalDesign": design,
            "growthFacility": facility,
            "documentationURL": study.get("map_of_experimental_design"),
        }
    )


def _observation_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Build a BrAPI ``observationUnit`` from a miappe ObservationUnit."""
    level = _clean(
        {
            "levelName": unit.get("observation_level")
            or unit.get("observation_unit_type"),
            "levelCode": unit.get("observation_level_code"),
        }
    )
    # BrAPI v2: block/replicate are expressed via observationLevelRelationships.
    relationships = []
    if unit.get("observation_unit_block"):
        relationships.append(
            {"levelName": "block", "levelCode": str(unit["observation_unit_block"])}
        )
    if unit.get("observation_unit_replicate"):
        relationships.append(
            {"levelName": "rep", "levelCode": str(unit["observation_unit_replicate"])}
        )
    position = _clean(
        {
            "positionCoordinateX": unit.get("observation_unit_x_ref"),
            "positionCoordinateXType": unit.get("spatial_distribution_type"),
            "positionCoordinateY": unit.get("observation_unit_y_ref"),
            "entryType": unit.get("entry_type"),
        }
    )
    # BrAPI v2 nests the level inside the position object.
    if level:
        position["observationLevel"] = level
    if relationships:
        position["observationLevelRelationships"] = relationships
    return _clean(
        {
            "observationUnitDbId": unit.get("unique_id"),
            "studyDbId": unit.get("study_id"),
            "germplasmDbId": unit.get("biological_material_id"),
            "observationUnitPosition": position,
        }
    )


def _germplasm(material: dict[str, Any]) -> dict[str, Any]:
    """Build a BrAPI ``germplasm`` from a miappe BiologicalMaterial."""
    germplasm_id = material.get("unique_id")
    study_id = material.get("study_id")
    return _clean(
        {
            "germplasmDbId": germplasm_id,
            "germplasmName": material.get("biological_material_description")
            or germplasm_id,
            "genus": material.get("genus"),
            "species": material.get("species"),
            "subtaxa": material.get("infraspecific_name"),
            "accessionNumber": material.get("accession_number"),
            "instituteCode": material.get("material_source_institute_code"),
            "instituteName": material.get("material_source_institute_name"),
            "studyDbIds": [study_id] if study_id else [],
        }
    )


def to_brapi(client: MetaseedClient) -> dict[str, list[dict[str, Any]]]:
    """Render a ``miappe``-profile dataset as BrAPI v2 JSON objects.

    Args:
        client: A MetaseedClient bound to the ``miappe`` profile.

    Returns:
        Mapping of BrAPI collection name to the list of v2 objects (the POST
        request bodies a BrAPI server accepts), e.g.
        ``{"trials": [...], "studies": [...], "observationUnits": [...],
        "germplasm": [...]}``. Only non-empty collections are included.
    """
    entities = client.serialize()["entities"]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(entity["_type"], []).append(entity)

    builders: dict[str, tuple[str, Any]] = {
        "Investigation": ("trials", _trial),
        "Study": ("studies", _study),
        "ObservationUnit": ("observationUnits", _observation_unit),
        "BiologicalMaterial": ("germplasm", _germplasm),
    }

    result: dict[str, list[dict[str, Any]]] = {}
    for entity_type, (collection, build) in builders.items():
        objects = [build(e) for e in by_type.get(entity_type, [])]
        if objects:
            result[collection] = objects
    return result
