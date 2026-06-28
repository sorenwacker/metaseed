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

from metaseed.metabolights.mapper import build_dataset

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.metabolights.client import MetaboLightsClient

__all__ = ["build_dataset", "import_accession"]


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
        Factors, Protocols, Samples, and Assays). Call
        :meth:`~metaseed.api.client.MetaseedClient.validate` to report gaps.
    """
    from metaseed.metabolights.client import MetaboLightsClient

    client = client or MetaboLightsClient()
    document = client.study(accession)
    return build_dataset(document, version=version)
