"""BrAPI (Breeding API) importer.

Fetches plant-breeding metadata from any [BrAPI](https://brapi.org) v2 server and
maps it into a ``miappe``-profile dataset. Data files are referenced via their
URLs, never downloaded. The address names what to import: the server's base
URL for every study it holds, a trial's address for that trial's studies, or a
study's address for that one study.

    >>> from metaseed.brapi import import_brapi
    >>> base = "https://test-server.brapi.org/brapi/v2"
    >>> client = import_brapi(base)            # needs metaseed[brapi]
    >>> trial = import_brapi(f"{base}/trials/trial1")
    >>> client.validate()

``build_dataset`` (the pure mapper) is importable without the ``metaseed[brapi]``
extra; ``import_brapi`` needs ``httpx``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from metaseed.brapi.export import to_brapi
from metaseed.brapi.mapper import build_dataset

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.brapi.client import BrapiClient

__all__ = ["BrapiAddress", "build_dataset", "import_brapi", "parse_address", "to_brapi"]


@dataclass(frozen=True)
class BrapiAddress:
    """What a BrAPI address names: the server, or one trial or study on it."""

    base_url: str
    trial_db_id: str | None = None
    study_db_id: str | None = None


def parse_address(address: str) -> BrapiAddress:
    """Read a server base URL, a trial's address or a study's address.

    A trial's address is ``<base>/trials/<trialDbId>`` and a study's
    ``<base>/studies/<studyDbId>``, with the identifier as the server spells
    it in a URL. Any other resource below the base URL is refused: given a
    trial's address, the importer used to append ``/studies`` to it, and a
    server that ignored the extra segments answered with every study it held.

    Raises:
        ValueError: For an address naming anything but the server, a trial or
            a study, with the base URL to enter instead.
    """
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(address)
    segments = [segment for segment in parts.path.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment.lower() not in _RESOURCES:
            continue
        base = urlunsplit(
            (parts.scheme, parts.netloc, "/" + "/".join(segments[:index]), "", "")
        )
        record = segments[index + 1] if len(segments) > index + 1 else None
        if segment.lower() == "trials" and record and len(segments) == index + 2:
            return BrapiAddress(base, trial_db_id=record)
        if segment.lower() == "studies" and record and len(segments) == index + 2:
            return BrapiAddress(base, study_db_id=record)
        raise ValueError(
            f"'{address}' is not an address the import takes: enter the server's "
            f"base URL, which ends in /brapi/v2 ({base}), a trial's address "
            f"({base}/trials/<trialDbId>) or a study's ({base}/studies/<studyDbId>)."
        )
    return BrapiAddress(address.rstrip("/"))


#: BrAPI resources an address may name below the base URL.
_RESOURCES = frozenset(
    {"trials", "studies", "germplasm", "observationunits", "observations", "programs"}
)


def import_brapi(
    address: str,
    *,
    study_db_id: str | None = None,
    token: str | None = None,
    client: BrapiClient | None = None,
    version: str = "1.2",
) -> MetaseedClient:
    """Import a BrAPI v2 server, trial or study into a ``miappe``-profile dataset.

    Args:
        address: The server's base URL (e.g.
            ``https://test-server.brapi.org/brapi/v2``), which imports every
            study the server exposes; a trial's address
            (``<base>/trials/<trialDbId>``), which imports that trial's
            studies; or a study's address (``<base>/studies/<studyDbId>``).
        study_db_id: Optional ``studyDbId`` to restrict a server import to one
            study, kept for callers that hold the identifier rather than the
            address.
        token: Optional bearer token for authenticated servers.
        client: Optional pre-configured
            :class:`~metaseed.brapi.client.BrapiClient`.
        version: ``miappe`` profile version.

    Returns:
        A :class:`~metaseed.api.client.MetaseedClient` holding the imported
        Investigations, Studies, BiologicalMaterials, ObservationUnits,
        ObservedVariables, and DataFile references. Call
        :meth:`~metaseed.api.client.MetaseedClient.validate` to report gaps.

    Raises:
        ValueError: If the address names anything but a server, a trial or a
            study.
    """
    from metaseed.brapi.client import BrapiClient

    where = parse_address(address)
    client = client or BrapiClient(where.base_url, token=token)

    if where.trial_db_id is not None:
        listed = client.trial(where.trial_db_id).get("studies") or []
        studies = [
            client.study(entry["studyDbId"])
            for entry in listed
            if isinstance(entry, dict) and entry.get("studyDbId")
        ]
    elif where.study_db_id is not None:
        studies = [client.study(where.study_db_id)]
    else:
        studies = client.studies()
        if study_db_id is not None:
            studies = [s for s in studies if s.get("studyDbId") == study_db_id]
    study_ids = [s["studyDbId"] for s in studies if s.get("studyDbId")]
    scoped = where.trial_db_id is not None or where.study_db_id is not None

    observation_units: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    germplasm: list[dict[str, Any]] = []
    seen_germplasm: set[str] = set()
    for study_id in study_ids:
        units = client.observation_units(study_id)
        observation_units.extend(units)
        # Asked for the study first, which is one request where the server
        # honours the filter (FAIDARE does). Not every server does: the BrAPI
        # reference server answers with nothing, which once imported a dataset
        # with no measurements at all. Then one request per unit we already
        # have, and a measurement a server lists under more than one unit is
        # imported once.
        seen_observations: set[str] = set()
        found = client.observations_for_study(study_id)
        if not found:
            found = [
                observation
                for unit in units
                if unit.get("observationUnitDbId")
                for observation in client.observations_for_unit(
                    unit["observationUnitDbId"]
                )
            ]
        for observation in found:
            key = observation.get("observationDbId")
            if key is not None:
                if key in seen_observations:
                    continue
                seen_observations.add(str(key))
            observations.append(observation)
        if scoped:
            # The germplasm of these studies, not of the whole server; a study
            # may share accessions with the one before it.
            for item in client.germplasm(study_id):
                key = str(item.get("germplasmDbId") or "")
                if key and key in seen_germplasm:
                    continue
                seen_germplasm.add(key)
                germplasm.append(item)

    if not scoped:
        germplasm = client.germplasm()

    return build_dataset(
        studies, observation_units, observations, germplasm, version=version
    )
