"""BrAPI (Breeding API) importer.

Fetches plant-breeding metadata from any [BrAPI](https://brapi.org) v2 server and
maps it into a ``miappe``-profile dataset. Data files are referenced via their
URLs, never downloaded.

    >>> from metaseed.brapi import import_brapi
    >>> base = "https://test-server.brapi.org/brapi/v2"
    >>> client = import_brapi(base)            # needs metaseed[brapi]
    >>> client.validate()

``build_dataset`` (the pure mapper) is importable without the ``metaseed[brapi]``
extra; ``import_brapi`` needs ``httpx``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.brapi.export import to_brapi
from metaseed.brapi.mapper import build_dataset

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.brapi.client import BrapiClient

__all__ = ["build_dataset", "import_brapi", "to_brapi"]


def import_brapi(
    base_url: str,
    *,
    study_db_id: str | None = None,
    token: str | None = None,
    client: BrapiClient | None = None,
    version: str = "1.2",
) -> MetaseedClient:
    """Import a BrAPI v2 server's metadata into a ``miappe``-profile dataset.

    Args:
        base_url: BrAPI v2 base URL (e.g.
            ``https://test-server.brapi.org/brapi/v2``).
        study_db_id: Optional ``studyDbId`` to restrict the import to one study.
            When omitted, every study the server exposes is imported.
        token: Optional bearer token for authenticated servers.
        client: Optional pre-configured
            :class:`~metaseed.brapi.client.BrapiClient`.
        version: ``miappe`` profile version.

    Returns:
        A :class:`~metaseed.api.client.MetaseedClient` holding the imported
        Investigations, Studies, BiologicalMaterials, ObservationUnits,
        ObservedVariables, and DataFile references. Call
        :meth:`~metaseed.api.client.MetaseedClient.validate` to report gaps.
    """
    from metaseed.brapi.client import BrapiClient

    client = client or BrapiClient(base_url, token=token)

    studies = client.studies()
    if study_db_id is not None:
        studies = [s for s in studies if s.get("studyDbId") == study_db_id]
        study_ids = [study_db_id]
    else:
        study_ids = [s["studyDbId"] for s in studies if s.get("studyDbId")]

    observation_units: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for study_id in study_ids:
        units = client.observation_units(study_id)
        observation_units.extend(units)
        # Collected per observation unit, not per study: servers do not reliably
        # honour a studyDbId filter on /observations (the BrAPI reference server
        # returns nothing), which silently imported a dataset with no
        # measurements at all. One request per unit we already have.
        seen_observations: set[str] = set()
        for unit in units:
            unit_id = unit.get("observationUnitDbId")
            if not unit_id:
                continue
            for observation in client.observations_for_unit(unit_id):
                # Guard against a server returning one observation under more
                # than one unit: per-unit collection would otherwise import the
                # same measurement twice.
                key = observation.get("observationDbId")
                if key is not None:
                    if key in seen_observations:
                        continue
                    seen_observations.add(str(key))
                observations.append(observation)

    germplasm = client.germplasm()

    return build_dataset(
        studies, observation_units, observations, germplasm, version=version
    )
