"""Map ENA Portal API ``read_run`` records into an ``ena``-profile dataset.

Pure and network-free: it takes already-fetched rows (as returned by the ENA
Portal API ``filereport`` endpoint with ``result=read_run``) and builds a
:class:`~metaseed.api.client.MetaseedClient` bound to the ``ena`` profile. Raw
sequence files are *referenced* (their FTP URLs become ``File`` entities), never
downloaded.

Accessions are used as the entity ``alias`` (the identifier the ``*_ref`` fields
resolve against), so samples/experiments/runs/files auto-link to their parents.
Entities are created with ``skip_validation`` — an import should not fail on a
record that omits a field; call :meth:`MetaseedClient.validate` to report gaps.
"""

from __future__ import annotations

from itertools import zip_longest
from typing import TYPE_CHECKING, Any

from metaseed.mapping import clean as _clean

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient

# ENA Portal `read_run` fields this mapper consumes. Request these via the
# client so every row carries what the entities need.
READ_RUN_FIELDS: tuple[str, ...] = (
    "study_accession",
    "study_title",
    "sample_accession",
    "sample_alias",
    "tax_id",
    "scientific_name",
    "experiment_accession",
    "library_name",
    "library_strategy",
    "library_source",
    "library_selection",
    "library_layout",
    "instrument_platform",
    "instrument_model",
    "run_accession",
    "fastq_ftp",
    "fastq_md5",
)


def _int(value: Any) -> int | None:
    """Coerce an ENA numeric string (e.g. tax_id) to int, else None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_dataset(
    rows: list[dict[str, Any]], *, version: str = "1.0"
) -> MetaseedClient:
    """Build an ``ena``-profile dataset from ENA ``read_run`` rows.

    Args:
        rows: ENA Portal ``read_run`` records (one per run).
        version: ``ena`` profile version.

    Returns:
        A MetaseedClient holding the Study and its Samples, Experiments, Runs,
        and File references. Empty if ``rows`` is empty.
    """
    from metaseed import MetaseedClient

    client = MetaseedClient("ena", version)
    if not rows:
        return client

    study_acc = rows[0].get("study_accession")
    client.create_entity(
        "Study",
        _clean(
            {
                "alias": study_acc,
                "accession": study_acc,
                "title": rows[0].get("study_title") or study_acc,
                "description": rows[0].get("study_title") or study_acc,
            }
        ),
        skip_validation=True,
    )

    seen_samples: set[str] = set()
    seen_experiments: set[str] = set()

    for row in rows:
        sample_acc = row.get("sample_accession")
        if sample_acc and sample_acc not in seen_samples:
            seen_samples.add(sample_acc)
            client.create_entity(
                "Sample",
                _clean(
                    {
                        "alias": sample_acc,
                        "accession": sample_acc,
                        "study_ref": study_acc,
                        "title": row.get("sample_alias") or row.get("scientific_name"),
                        "taxon_id": _int(row.get("tax_id")),
                        "scientific_name": row.get("scientific_name"),
                    }
                ),
                skip_validation=True,
            )

        exp_acc = row.get("experiment_accession")
        if exp_acc and exp_acc not in seen_experiments:
            seen_experiments.add(exp_acc)
            client.create_entity(
                "Experiment",
                _clean(
                    {
                        "alias": exp_acc,
                        "accession": exp_acc,
                        "study_ref": study_acc,
                        "sample_ref": sample_acc,
                        "library_name": row.get("library_name"),
                        "library_strategy": row.get("library_strategy"),
                        "library_source": row.get("library_source"),
                        "library_selection": row.get("library_selection"),
                        "library_layout": row.get("library_layout"),
                        "platform": row.get("instrument_platform"),
                        "instrument_model": row.get("instrument_model"),
                    }
                ),
                skip_validation=True,
            )

        run_acc = row.get("run_accession")
        if not run_acc:
            continue
        client.create_entity(
            "Run",
            _clean({"alias": run_acc, "accession": run_acc, "experiment_ref": exp_acc}),
            skip_validation=True,
        )

        # fastq_ftp and fastq_md5 are parallel ;-separated lists; pair them
        # positionally (zip_longest) so an empty URL segment cannot shift the
        # checksums out of alignment.
        urls = (row.get("fastq_ftp") or "").split(";")
        md5s = (row.get("fastq_md5") or "").split(";")
        for url, md5 in zip_longest(urls, md5s, fillvalue=""):
            if not url:
                continue
            client.create_entity(
                "File",
                _clean(
                    {
                        "run_ref": run_acc,
                        "filename": url.rsplit("/", 1)[-1],
                        "filetype": "fastq",
                        "checksum_method": "MD5",
                        "checksum": md5 or None,
                    }
                ),
                skip_validation=True,
            )

    return client
