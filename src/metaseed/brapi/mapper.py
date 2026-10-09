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

from metaseed.mapping import clean as _clean

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


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


#: MIAPPE's entry types and growth facility types, as the profile's
#: vocabulary rules spell them. BrAPI servers return what their database
#: holds: Breedbase an entry type in capitals, FAIDARE a facility as a list
#: of CO_715 descriptions ("field environment condition, greenhouse").
ENTRY_TYPES = ("test", "check", "filler")
GROWTH_FACILITY_TYPES = (
    "field",
    "greenhouse",
    "glasshouse",
    "growth chamber",
    "phytotron",
    "open top chamber",
)


def _entry_type(value: Any) -> Any:
    """The entry type in MIAPPE's spelling where it is one, else as sent."""
    if isinstance(value, str) and value.strip().lower() in ENTRY_TYPES:
        return value.strip().lower()
    return value


def _growth_facility_type(value: Any) -> Any:
    """The MIAPPE facility type a server's description names, else as sent.

    An exact match wins; otherwise the first vocabulary term the description
    contains, in the description's own order, so "field environment
    condition, greenhouse" reads as a field.
    """
    if not isinstance(value, str):
        return value
    text = value.strip().lower()
    if text in GROWTH_FACILITY_TYPES:
        return text
    found = [(text.find(term), term) for term in GROWTH_FACILITY_TYPES if term in text]
    return min(found)[1] if found else value


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
                    "growth_facility_type": _growth_facility_type(
                        (study.get("growthFacility") or {}).get("description")
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
        position = unit.get("observationUnitPosition") or {}
        # In BrAPI v2 the observationLevel object is nested inside the position,
        # and block/replicate are expressed via observationLevelRelationships.
        level = _level(position.get("observationLevel"))
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
                    "observation_unit_block": _level_code(position, ("block",)),
                    "observation_unit_replicate": _level_code(
                        position, ("rep", "replicate")
                    ),
                    "entry_type": _entry_type(position.get("entryType")),
                }
            ),
            skip_validation=True,
        )


def _level(level: Any) -> dict[str, Any]:
    """The unit's level as ``levelName`` and ``levelCode``, however the server put it.

    BrAPI names the level (``plot``) in ``levelName`` and numbers it in
    ``levelCode``. FAIDARE puts the number in ``levelName`` and the path of
    level names in ``levelOrder`` (``REPLICATE>BLOCK>PLOT``), whose last
    segment is the level.
    """
    if not isinstance(level, dict):
        return {}
    order = level.get("levelOrder")
    name = level.get("levelName")
    if (
        isinstance(order, str)
        and ">" in order
        and (name is None or str(name).isdigit())
    ):
        return {"levelName": order.rsplit(">", 1)[-1].lower(), "levelCode": name}
    return level


def _relationships(position: dict[str, Any]) -> list[tuple[str, str | None]]:
    """``(level name, code)`` per relationship, from objects or FAIDARE's strings.

    BrAPI lists objects with ``levelName`` and ``levelCode``. FAIDARE lists
    strings, one per unit, of the form
    ``REPLICATE>BLOCK>PLOT:223977,REPLICATE>BLOCK:5,REPLICATE:2``: a level path
    and its code per comma, the level being the path's last segment.
    """
    found: list[tuple[str, str | None]] = []
    for rel in position.get("observationLevelRelationships") or []:
        if isinstance(rel, dict):
            code = rel.get("levelCode")
            found.append(
                (
                    str(rel.get("levelName", "")).lower(),
                    str(code) if code is not None else None,
                )
            )
        elif isinstance(rel, str):
            for piece in rel.split(","):
                path, _, code = piece.strip().rpartition(":")
                if path:
                    found.append((path.rsplit(">", 1)[-1].lower(), code or None))
    return found


def _level_code(position: dict[str, Any], level_names: tuple[str, ...]) -> str | None:
    """Return the levelCode for a named level from observationLevelRelationships."""
    for name, code in _relationships(position):
        if name in level_names:
            return code
    return None


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
