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
        observation_units.extend(client.observation_units(study_id))
        observations.extend(client.observations(study_id))

    germplasm = client.germplasm()

    return build_dataset(
        studies, observation_units, observations, germplasm, version=version
    )
