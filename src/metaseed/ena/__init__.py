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

import logging
import re
from typing import TYPE_CHECKING

from metaseed.ena.export import to_ena_xml
from metaseed.ena.mapper import build_dataset

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.ena.client import EnaClient

__all__ = ["build_dataset", "import_accession", "to_ena_xml"]

logger = logging.getLogger(__name__)

#: A primary (PRJEB...) or secondary (ERP...) study accession: the only kind the
#: Portal's ``study`` and ``analysis`` results accept.
STUDY_ACCESSION = re.compile(r"^(PRJ[A-Z]{2}[0-9]+|[EDSR]RP[0-9]{6,})$")


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
        Study and its Samples, Experiments, Runs, Analyses and File references.
        Call :meth:`~metaseed.api.client.MetaseedClient.validate` to report
        gaps.
    """
    from metaseed.ena.client import EnaClient

    client = client or EnaClient()
    # Three requests per import, one per Portal result, whatever the study
    # holds. The study and analysis results accept only a study accession,
    # so a run, sample or experiment accession is resolved to its study
    # through the runs first. The Portal answers an empty result with an
    # empty list; the counts are logged so an absence is visibly an answer
    # rather than a query not made.
    runs = client.read_run(accession)
    study_accession = runs[0].get("study_accession") if runs else None
    if study_accession is None and STUDY_ACCESSION.match(accession):
        study_accession = accession
    study = client.study(study_accession) if study_accession else []
    analyses = client.analysis(study_accession) if study_accession else []
    logger.info(
        "%s: %d study records, %d runs, %d analyses",
        accession,
        len(study),
        len(runs),
        len(analyses),
    )
    return build_dataset(runs, study=study, analyses=analyses, version=version)
