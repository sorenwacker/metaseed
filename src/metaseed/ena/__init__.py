"""ENA (European Nucleotide Archive) importer.

Fetches public metadata for an ENA accession and maps it into a validated
``ena``-profile dataset. Raw sequence files are referenced, never downloaded.

    >>> from metaseed.ena import import_accession
    >>> client = import_accession("PRJEB10000")   # needs metaseed[ena]
    >>> client.validate()

``build_dataset`` (the pure mapper) is importable without the ``metaseed[ena]``
extra; ``import_accession`` needs ``httpx``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaseed.ena.export import to_ena_xml
from metaseed.ena.mapper import build_dataset

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.ena.client import EnaClient

__all__ = ["build_dataset", "import_accession", "to_ena_xml"]


def import_accession(
    accession: str,
    *,
    version: str = "1.0",
    client: EnaClient | None = None,
) -> MetaseedClient:
    """Import an ENA accession into an ``ena``-profile dataset.

    Args:
        accession: An ENA accession resolvable to runs (study, sample,
            experiment, or run).
        version: ``ena`` profile version.
        client: Optional pre-configured :class:`~metaseed.ena.client.EnaClient`.

    Returns:
        A :class:`~metaseed.api.client.MetaseedClient` holding the imported
        Study and its Samples, Experiments, Runs, and File references. Call
        :meth:`~metaseed.api.client.MetaseedClient.validate` to report gaps.
    """
    from metaseed.ena.client import EnaClient

    client = client or EnaClient()
    rows = client.read_run(accession)
    return build_dataset(rows, version=version)
