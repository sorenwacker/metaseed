"""PRIDE Archive importer.

Fetches public metadata for a ProteomeXchange (PXD) accession and maps it into a
``pride``-profile dataset. Data files (RAW/mzML/peak lists) are referenced, never
downloaded.

    >>> from metaseed.pride import import_accession
    >>> client = import_accession("PXD000001")   # needs metaseed[pride]
    >>> client.validate()

``build_dataset`` (the pure mapper) is importable without the ``metaseed[pride]``
extra; ``import_accession`` needs ``httpx``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaseed.pride.export import to_pride_submission
from metaseed.pride.mapper import build_dataset

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.pride.client import PrideClient

__all__ = ["build_dataset", "import_accession", "to_pride_submission"]


def import_accession(
    accession: str,
    *,
    version: str = "1.0",
    client: PrideClient | None = None,
) -> MetaseedClient:
    """Import a PRIDE project into a ``pride``-profile dataset.

    Args:
        accession: A ProteomeXchange accession (e.g. ``"PXD000001"``).
        version: ``pride`` profile version.
        client: Optional pre-configured
            :class:`~metaseed.pride.client.PrideClient`.

    Returns:
        A :class:`~metaseed.api.client.MetaseedClient` holding the imported
        Dataset with its nested entities and referenced data files. Call
        :meth:`~metaseed.api.client.MetaseedClient.validate` to report gaps.
    """
    from metaseed.pride.client import PrideClient

    client = client or PrideClient()
    project = client.project(accession)
    files = client.files(accession)
    return build_dataset(project, files, version=version)
