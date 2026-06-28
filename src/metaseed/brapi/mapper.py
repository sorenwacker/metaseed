"""Map BrAPI v2 objects into a ``miappe``-profile dataset.

Pure and network-free: it takes already-fetched BrAPI objects (as returned by a
BrAPI v2 server under ``result.data``) and builds a
:class:`~metaseed.api.client.MetaseedClient` bound to the ``miappe`` profile.
Data files are *referenced* (BrAPI ``dataLinks`` become ``DataFile`` entities
holding their URLs), never downloaded.

BrAPI ``DbId`` values are used as each entity's ``unique_id`` (the identifier the
``*_id`` reference fields resolve against), so studies, observation units,
biological materials, and observed variables auto-link to their parents.
Entities are created with ``skip_validation`` — an import should not fail on a
record that omits a field; call :meth:`MetaseedClient.validate` to report gaps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values so missing BrAPI fields are absent, not blank."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def build_dataset(
    studies: list[dict[str, Any]],
    observation_units: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    germplasm: list[dict[str, Any]],
    *,
    version: str = "1.2",
) -> MetaseedClient:
    """Build a ``miappe``-profile dataset from BrAPI v2 objects.

    Args:
        studies: BrAPI ``studies`` objects (one per study).
        observation_units: BrAPI ``observationunits`` objects.
        observations: BrAPI ``observations`` objects.
        germplasm: BrAPI ``germplasm`` objects.
        version: ``miappe`` profile version.

    Returns:
        A MetaseedClient holding Investigations and their Studies,
        BiologicalMaterials, ObservationUnits, ObservedVariables, and DataFile
        references. Empty if every input list is empty.
    """
    from metaseed import MetaseedClient

    client = MetaseedClient("miappe", version)

    default_study_id = studies[0].get("studyDbId") if studies else None

    _add_investigations_and_studies(client, studies)
    _add_germplasm(client, germplasm, default_study_id)
    _add_observation_units(client, observation_units)
    _add_observed_variables(client, observations, default_study_id)
    _add_data_files(client, studies)

    return client


def _trial_id(study: dict[str, Any]) -> str | None:
    """Return the Investigation id for a study (its trial, else itself)."""
    return study.get("trialDbId") or study.get("studyDbId")


def _add_investigations_and_studies(
    client: MetaseedClient, studies: list[dict[str, Any]]
) -> None:
    """Create one Investigation per distinct BrAPI trial, then each Study."""
    seen_trials: set[str] = set()
    for study in studies:
        trial_id = _trial_id(study)
        if trial_id and trial_id not in seen_trials:
            seen_trials.add(trial_id)
            client.create_entity(
                "Investigation",
                _clean(
                    {
                        "unique_id": trial_id,
                        "title": study.get("trialName") or trial_id,
                    }
                ),
                skip_validation=True,
            )

    for study in studies:
        study_id = study.get("studyDbId")
        if not study_id:
            continue
        design = study.get("experimentalDesign") or {}
        client.create_entity(
            "Study",
            _clean(
                {
                    "unique_id": study_id,
                    "investigation_id": _trial_id(study),
                    "title": study.get("studyName") or study_id,
                    "description": study.get("studyDescription"),
                    "start_date": study.get("startDate"),
                    "end_date": study.get("endDate"),
                    "experimental_site_name": study.get("locationName"),
                    "experimental_design_type": design.get("PUI"),
                    "experimental_design_description": design.get("description"),
                    "growth_facility_type": (study.get("growthFacility") or {}).get(
                        "description"
                    ),
                    "map_of_experimental_design": study.get("documentationURL"),
                }
            ),
            skip_validation=True,
        )


def _add_germplasm(
    client: MetaseedClient,
    germplasm: list[dict[str, Any]],
    default_study_id: str | None,
) -> None:
    """Create a BiologicalMaterial per BrAPI germplasm object."""
    for item in germplasm:
        germplasm_id = item.get("germplasmDbId")
        if not germplasm_id:
            continue
        study_ids = item.get("studyDbIds") or []
        study_id = study_ids[0] if study_ids else default_study_id
        client.create_entity(
            "BiologicalMaterial",
            _clean(
                {
                    "unique_id": germplasm_id,
                    "study_id": study_id,
                    "organism": item.get("species"),
                    "genus": item.get("genus"),
                    "species": item.get("species"),
                    "infraspecific_name": item.get("subtaxa"),
                    "accession_number": item.get("accessionNumber"),
                    "biological_material_description": item.get("germplasmName"),
                    "material_source_institute_code": item.get("instituteCode"),
                    "material_source_institute_name": item.get("instituteName"),
                }
            ),
            skip_validation=True,
        )


def _add_observation_units(
    client: MetaseedClient, observation_units: list[dict[str, Any]]
) -> None:
    """Create an ObservationUnit per BrAPI observation unit."""
    for unit in observation_units:
        unit_id = unit.get("observationUnitDbId")
        if not unit_id:
            continue
        level = unit.get("observationLevel") or {}
        position = unit.get("observationUnitPosition") or {}
        client.create_entity(
            "ObservationUnit",
            _clean(
                {
                    "unique_id": unit_id,
                    "study_id": unit.get("studyDbId"),
                    "biological_material_id": unit.get("germplasmDbId"),
                    "observation_unit_type": level.get("levelName"),
                    "observation_level": level.get("levelName"),
                    "observation_level_code": level.get("levelCode"),
                    "spatial_distribution_type": position.get(
                        "positionCoordinateXType"
                    ),
                    "observation_unit_x_ref": position.get("positionCoordinateX"),
                    "observation_unit_y_ref": position.get("positionCoordinateY"),
                    "observation_unit_block": position.get("blockNumber"),
                    "observation_unit_replicate": position.get("replicate"),
                    "entry_type": position.get("entryType"),
                }
            ),
            skip_validation=True,
        )


def _add_observed_variables(
    client: MetaseedClient,
    observations: list[dict[str, Any]],
    default_study_id: str | None,
) -> None:
    """Create one ObservedVariable per distinct variable referenced.

    BrAPI ``observations`` carry measured values, for which MIAPPE 1.2 has no
    dedicated entity; they are reduced to the distinct ObservedVariable
    definitions they reference.
    """
    seen: set[str] = set()
    for obs in observations:
        variable_id = obs.get("observationVariableDbId")
        if not variable_id or variable_id in seen:
            continue
        seen.add(variable_id)
        client.create_entity(
            "ObservedVariable",
            _clean(
                {
                    "unique_id": variable_id,
                    "study_id": obs.get("studyDbId") or default_study_id,
                    "name": obs.get("observationVariableName"),
                    "trait": obs.get("observationVariableName"),
                }
            ),
            skip_validation=True,
        )


def _add_data_files(client: MetaseedClient, studies: list[dict[str, Any]]) -> None:
    """Reference each study's BrAPI ``dataLinks`` as a DataFile entity."""
    for study in studies:
        study_id = study.get("studyDbId")
        for link in study.get("dataLinks") or []:
            url = link.get("url")
            if not url:
                continue
            client.create_entity(
                "DataFile",
                _clean(
                    {
                        "unique_id": url.rsplit("/", 1)[-1] or url,
                        "study_id": study_id,
                        "name": link.get("name") or url.rsplit("/", 1)[-1],
                        "link": url,
                        "description": link.get("description"),
                        "file_type": link.get("type"),
                    }
                ),
                skip_validation=True,
            )
