"""MetaboLights importer.

Fetches public metadata for a MetaboLights study accession and maps it into a
validated ``metabolights``-profile dataset. Raw spectra files are referenced,
never downloaded.

    >>> from metaseed.metabolights import import_accession
    >>> client = import_accession("MTBLS1")   # needs metaseed[metabolights]
    >>> client.validate()

``build_dataset`` (the pure mapper) is importable without the
``metaseed[metabolights]`` extra; ``import_accession`` needs ``httpx``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaseed.metabolights.export import to_metabolights
from metaseed.metabolights.mapper import build_dataset
from metaseed.metabolights.validate import validate_cv

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.metabolights.client import MetaboLightsClient

__all__ = ["build_dataset", "import_accession", "to_metabolights", "validate_cv"]


def import_accession(
    accession: str,
    *,
    version: str = "1.0",
    client: MetaboLightsClient | None = None,
) -> MetaseedClient:
    """Import a MetaboLights study into a ``metabolights``-profile dataset.

    Args:
        accession: A MetaboLights study accession (e.g. ``"MTBLS1"``).
        version: ``metabolights`` profile version.
        client: Optional pre-configured
            :class:`~metaseed.metabolights.client.MetaboLightsClient`.

    Returns:
        A :class:`~metaseed.api.client.MetaseedClient` holding the imported
        Investigation and its Contacts, Publications, and Studies (with their
        Factors, Protocols, Samples, and Assays). The Samples (with their
        Characteristics and Factor Values), the Assays' DataFiles, and their
        Metabolites are recovered from the study's ISA-Tab files, which are
        available only for public studies; an embargoed study imports the
        ISA-JSON backbone only. Call
        :meth:`~metaseed.api.client.MetaseedClient.validate` to report gaps.
    """
    import httpx

    from metaseed.metabolights.client import MetaboLightsClient

    client = client or MetaboLightsClient()
    document = client.study(accession)
    # The ISA-JSON document leaves samples/dataFiles empty; recover them from the
    # study's ISA-Tab files. Only public studies expose these on the FTP root, so
    # degrade to the (metadata-only) ISA-JSON import if they are unavailable.
    try:
        isatab_files = client.study_files(accession)
    except (httpx.HTTPError, OSError):
        isatab_files = {}
    return build_dataset(document, version=version, isatab_files=isatab_files)
