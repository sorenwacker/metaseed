"""Map ENA Portal API ``read_run`` records into an ``ena``-profile dataset.

Pure and network-free: it takes already-fetched rows (as returned by the ENA
Portal API ``filereport`` endpoint with ``result=read_run`` and ``fields=all``)
and builds a :class:`~metaseed.api.client.MetaseedClient` bound to the ``ena``
profile. Raw sequence files are *referenced* (their FTP URLs become ``File``
entities), never downloaded.

Every non-empty column of a row reaches the dataset. A column the ``ena``
profile declares a field for fills that field; a column without one becomes an
attribute (``SampleAttribute``, ``ExperimentAttribute`` or ``RunAttribute``)
carrying the ENA column name as its ``tag`` and ENA's value verbatim. Which
entity owns a column is ENA's answer rather than this module's: the columns ENA
publishes under ``result=sample`` belong to the Sample, an enumerated set of
library and sequencing descriptors belongs to the Experiment, and the Run is the
catch-all — so a column ENA adds after this release is carried rather than
dropped. The ``ena`` profile declares no study-level attribute entity, so a
study-level column without a declared field is carried as a run attribute.

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
    from collections.abc import Mapping

    from metaseed.api.client import MetaseedClient

# Columns ENA publishes under `result=sample`; recorded from the Portal's
# `returnFields` endpoint. A column here describes the sample, so one without a
# declared profile field becomes a SampleAttribute.
SAMPLE_COLUMNS: frozenset[str] = frozenset(
    (
        "age",
        "altitude",
        "assembly_quality",
        "assembly_software",
        "bio_material",
        "binning_software",
        "broad_scale_environmental_context",
        "broker_name",
        "cell_line",
        "cell_type",
        "center_name",
        "checklist",
        "collected_by",
        "collection_date",
        "collection_date_end",
        "collection_date_start",
        "completeness_score",
        "contamination_score",
        "country",
        "cultivar",
        "culture_collection",
        "datahub",
        "depth",
        "description",
        "dev_stage",
        "disease",
        "ecotype",
        "elevation",
        "environment_biome",
        "environment_feature",
        "environment_material",
        "environmental_medium",
        "environmental_sample",
        "experimental_factor",
        "first_public",
        "germline",
        "host",
        "host_body_site",
        "host_genotype",
        "host_gravidity",
        "host_growth_conditions",
        "host_phenotype",
        "host_scientific_name",
        "host_sex",
        "host_status",
        "host_tax_id",
        "identified_by",
        "investigation_type",
        "isolate",
        "isolation_source",
        "last_updated",
        "lat",
        "local_environmental_context",
        "location",
        "location_end",
        "location_start",
        "lon",
        "marine_region",
        "mating_type",
        "ncbi_reporting_standard",
        "ph",
        "project_name",
        "protocol_label",
        "salinity",
        "sample_accession",
        "sample_alias",
        "sample_capture_status",
        "sample_collection",
        "sample_description",
        "sample_material",
        "sample_title",
        "sampling_campaign",
        "sampling_platform",
        "sampling_site",
        "scientific_name",
        "secondary_sample_accession",
        "sequencing_method",
        "serotype",
        "serovar",
        "sex",
        "specimen_voucher",
        "status",
        "strain",
        "study_accession",
        "sub_species",
        "sub_strain",
        "submission_accession",
        "submission_tool",
        "submitted_host_sex",
        "surveillance_target",
        "tag",
        "target_gene",
        "tax_id",
        "tax_lineage",
        "taxonomic_classification",
        "taxonomic_identity_marker",
        "temperature",
        "tissue_lib",
        "tissue_type",
        "variety",
    )
)

# Library, protocol and sequencing descriptors: ENA does not publish these under
# `result=sample`, and they describe how the library was made rather than what
# was sequenced or when it was run.
EXPERIMENT_COLUMNS: frozenset[str] = frozenset(
    (
        "bisulfite_protocol",
        "cage_protocol",
        "chip_ab_provider",
        "chip_protocol",
        "chip_target",
        "control_experiment",
        "dnase_protocol",
        "experiment_alias",
        "experiment_target",
        "experimental_protocol",
        "extraction_protocol",
        "faang_library_selection",
        "hi_c_protocol",
        "library_gen_protocol",
        "library_max_fragment_size",
        "library_min_fragment_size",
        "library_pcr_isolation_protocol",
        "library_prep_date",
        "library_prep_date_format",
        "library_prep_latitude",
        "library_prep_location",
        "library_prep_longitude",
        "pcr_isolation_protocol",
        "read_strand",
        "restriction_enzyme",
        "restriction_enzyme_target_sequence",
        "restriction_site",
        "rna_integrity_num",
        "rna_prep_3_protocol",
        "rna_prep_5_protocol",
        "rna_purity_230_ratio",
        "rna_purity_280_ratio",
        "rt_prep_protocol",
        "sample_prep_interval",
        "sample_prep_interval_units",
        "sample_storage",
        "sample_storage_processing",
        "sequencing_date",
        "sequencing_date_format",
        "sequencing_location",
        "sequencing_longitude",
        "sequencing_primer_catalog",
        "sequencing_primer_lot",
        "sequencing_primer_provider",
        "transposase_protocol",
    )
)

# ENA column -> declared `ena`-profile field, per entity. A column named here is
# never also written as an attribute.
STUDY_FIELDS: Mapping[str, str] = {"broker_name": "broker_name"}

SAMPLE_FIELDS: Mapping[str, str] = {
    "sample_title": "title",
    "center_name": "center_name",
    "tax_id": "taxon_id",
    "scientific_name": "scientific_name",
    "sample_description": "description",
    "checklist": "checklist",
    "collection_date": "collection_date",
    "country": "geographic_location_country",
    "location": "lat_lon",
    "lat": "lat_lon_latitude",
    "lon": "lat_lon_longitude",
    "isolation_source": "isolation_source",
    "collected_by": "collected_by",
    "identified_by": "identified_by",
    "environmental_sample": "environmental_sample",
    "strain": "strain",
    "isolate": "isolate",
    "cultivar": "cultivar",
    "ecotype": "ecotype",
    "variety": "variety",
    "sub_species": "sub_species",
    "sex": "sex",
    "mating_type": "mating_type",
    "cell_type": "cell_type",
    "dev_stage": "dev_stage",
    "tissue_type": "tissue_type",
    "cell_line": "cell_line",
    "culture_collection": "culture_collection",
    "specimen_voucher": "specimen_voucher",
    "bio_material": "bio_material",
    "host": "host",
}

EXPERIMENT_FIELDS: Mapping[str, str] = {
    "experiment_title": "title",
    "library_name": "library_name",
    "library_strategy": "library_strategy",
    "library_source": "library_source",
    "library_selection": "library_selection",
    "library_layout": "library_layout",
    "library_construction_protocol": "library_construction_protocol",
    "nominal_length": "insert_size",
    "nominal_sdev": "insert_size_stddev",
    "instrument_platform": "platform",
    "instrument_model": "instrument_model",
}

RUN_FIELDS: Mapping[str, str] = {"run_date": "run_date"}

# The four file manifests ENA publishes per run: parallel ";"-separated lists of
# URLs and MD5 checksums. `submitted` carries its own format and read type; the
# others have a fixed type.
FILE_SETS: tuple[tuple[str, str, str | None], ...] = (
    ("fastq_ftp", "fastq_md5", "fastq"),
    ("submitted_ftp", "submitted_md5", None),
    ("sra_ftp", "sra_md5", "sra"),
    ("bam_ftp", "bam_md5", "bam"),
)

# File types the SRA schema accepts, spelled as it spells them. ENA's Portal
# reports the submitted format in upper case ("SFF", "BAM"), which the schema's
# enumeration rejects, so a reported format is matched case-insensitively and
# written back in the schema's spelling. Most are lower case, but the
# instrument-native ones are not, so lowercasing everything is not the fix.
SRA_FILETYPES: tuple[str, ...] = (
    "sra",
    "srf",
    "sff",
    "fastq",
    "fasta",
    "tab",
    "454_native",
    "454_native_seq",
    "454_native_qual",
    "Helicos_native",
    "Illumina_native",
    "Illumina_native_seq",
    "Illumina_native_prb",
    "Illumina_native_int",
    "Illumina_native_qseq",
    "Illumina_native_scarf",
    "SOLiD_native",
    "SOLiD_native_csfasta",
    "SOLiD_native_qual",
    "PacBio_HDF5",
    "bam",
    "cram",
    "CompleteGenomics_native",
    "OxfordNanopore_native",
)

_SRA_FILETYPE_BY_LOWERCASE = {filetype.lower(): filetype for filetype in SRA_FILETYPES}

# Compression suffixes to look past when reading a type off a filename.
COMPRESSION_SUFFIXES: frozenset[str] = frozenset(("gz", "bz2", "zip", "xz"))

# Columns consumed into entity identifiers or into File entities.
IDENTIFIER_COLUMNS: frozenset[str] = frozenset(
    (
        "study_accession",
        "study_title",
        "sample_accession",
        "experiment_accession",
        "run_accession",
    )
)

FILE_COLUMNS: frozenset[str] = frozenset(
    [column for url, md5, _ in FILE_SETS for column in (url, md5)]
    + ["submitted_format", "submitted_read_type"]
)

# Every column with a home of its own; the rest become attributes.
DECLARED_COLUMNS: frozenset[str] = (
    IDENTIFIER_COLUMNS
    | FILE_COLUMNS
    | frozenset(STUDY_FIELDS)
    | frozenset(SAMPLE_FIELDS)
    | frozenset(EXPERIMENT_FIELDS)
    | frozenset(RUN_FIELDS)
)


def _int(value: Any) -> int | None:
    """Coerce an ENA numeric string (e.g. tax_id) to int, else None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    """Coerce an ENA numeric string (e.g. lat) to float, else None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    """Coerce ENA's textual boolean to bool, else None."""
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


# Declared fields whose type is not a string.
FIELD_COERCERS: Mapping[str, Any] = {
    "taxon_id": _int,
    "insert_size": _int,
    "insert_size_stddev": _float,
    "lat_lon_latitude": _float,
    "lat_lon_longitude": _float,
    "environmental_sample": _bool,
}


def _filetype(reported: str | None, filename: str) -> str | None:
    """The file's type as the SRA schema spells it.

    Prefers the format ENA reports; falls back to the filename's extension when
    ENA reports none. A format the schema does not enumerate is passed through
    unchanged rather than replaced by a guess, and an unreadable one is left
    unset so ``validate()`` reports the gap.
    """
    if reported:
        return _SRA_FILETYPE_BY_LOWERCASE.get(reported.strip().lower(), reported)
    parts = [part for part in filename.lower().split(".") if part]
    while parts and parts[-1] in COMPRESSION_SUFFIXES:
        parts.pop()
    return _SRA_FILETYPE_BY_LOWERCASE.get(parts[-1]) if parts else None


def _fields(row: dict[str, Any], mapping: Mapping[str, str]) -> dict[str, Any]:
    """Map the row's non-empty columns onto declared profile fields."""
    values: dict[str, Any] = {}
    for column, field in mapping.items():
        value = row.get(column)
        if value in (None, ""):
            continue
        coerce = FIELD_COERCERS.get(field)
        values[field] = coerce(value) if coerce else value
    return values


def _owner(column: str) -> str:
    """The entity ENA's schema says a column describes."""
    if column in SAMPLE_COLUMNS:
        return "Sample"
    if column in EXPERIMENT_COLUMNS:
        return "Experiment"
    return "Run"


def _overflow(row: dict[str, Any]) -> dict[str, dict[str, str]]:
    """The row's columns with no declared field, grouped by owning entity."""
    buckets: dict[str, dict[str, str]] = {"Sample": {}, "Experiment": {}, "Run": {}}
    for column, value in row.items():
        if column in DECLARED_COLUMNS or value in (None, ""):
            continue
        buckets[_owner(column)][column] = str(value)
    return buckets


def _add_attributes(
    client: MetaseedClient,
    entity_type: str,
    parent_id: str,
    columns: Mapping[str, str],
) -> None:
    """Write each column as a ``tag``/``value`` attribute under its entity."""
    for tag, value in columns.items():
        client.create_entity(
            entity_type,
            {"tag": tag, "value": value},
            parent_id=parent_id,
            skip_validation=True,
        )


def _add_files(client: MetaseedClient, row: dict[str, Any], run_acc: str) -> None:
    """Reference every file ENA publishes for the run, across all four sets."""
    for url_column, md5_column, default_type in FILE_SETS:
        # The manifests are parallel ";"-separated lists; pair them positionally
        # (zip_longest) so an empty URL segment cannot shift the checksums out of
        # alignment.
        submitted = url_column == "submitted_ftp"
        urls = (row.get(url_column) or "").split(";")
        md5s = (row.get(md5_column) or "").split(";")
        # Only the submitted set carries its own per-file format.
        formats = (row.get("submitted_format") or "").split(";") if submitted else [""]
        for url, md5, reported_format in zip_longest(urls, md5s, formats, fillvalue=""):
            if not url:
                continue
            filename = url.rsplit("/", 1)[-1]
            client.create_entity(
                "File",
                _clean(
                    {
                        "run_ref": run_acc,
                        "filename": filename,
                        "filetype": _filetype(reported_format, filename)
                        if submitted
                        else default_type,
                        "checksum_method": "MD5",
                        "checksum": md5 or None,
                        "read_type": row.get("submitted_read_type")
                        if submitted
                        else None,
                    }
                ),
                skip_validation=True,
            )


def build_dataset(
    rows: list[dict[str, Any]], *, version: str = "1.0"
) -> MetaseedClient:
    """Build an ``ena``-profile dataset from ENA ``read_run`` rows.

    Args:
        rows: ENA Portal ``read_run`` records (one per run), as returned with
            ``fields=all``.
        version: ``ena`` profile version.

    Returns:
        A MetaseedClient holding the Study and its Samples, Experiments, Runs,
        File references and attributes. Empty if ``rows`` is empty.
    """
    from metaseed import MetaseedClient

    client = MetaseedClient("ena", version)
    if not rows:
        return client

    study_acc = rows[0].get("study_accession")
    study_title = rows[0].get("study_title") or study_acc
    client.create_entity(
        "Study",
        _clean(
            {
                "alias": study_acc,
                "accession": study_acc,
                "title": study_title,
                "description": study_title,
                **_fields(rows[0], STUDY_FIELDS),
            }
        ),
        skip_validation=True,
    )

    seen_samples: set[str] = set()
    seen_experiments: set[str] = set()

    for row in rows:
        overflow = _overflow(row)

        sample_acc = row.get("sample_accession")
        if sample_acc and sample_acc not in seen_samples:
            seen_samples.add(sample_acc)
            sample = client.create_entity(
                "Sample",
                _clean(
                    {
                        "alias": sample_acc,
                        "accession": sample_acc,
                        "study_ref": study_acc,
                        **_fields(row, SAMPLE_FIELDS),
                    }
                ),
                skip_validation=True,
            )
            _add_attributes(client, "SampleAttribute", sample.id, overflow["Sample"])

        exp_acc = row.get("experiment_accession")
        if exp_acc and exp_acc not in seen_experiments:
            seen_experiments.add(exp_acc)
            experiment = client.create_entity(
                "Experiment",
                _clean(
                    {
                        "alias": exp_acc,
                        "accession": exp_acc,
                        "study_ref": study_acc,
                        "sample_ref": sample_acc,
                        **_fields(row, EXPERIMENT_FIELDS),
                    }
                ),
                skip_validation=True,
            )
            _add_attributes(
                client,
                "ExperimentAttribute",
                experiment.id,
                overflow["Experiment"],
            )

        run_acc = row.get("run_accession")
        if not run_acc:
            continue
        run = client.create_entity(
            "Run",
            _clean(
                {
                    "alias": run_acc,
                    "accession": run_acc,
                    "experiment_ref": exp_acc,
                    **_fields(row, RUN_FIELDS),
                }
            ),
            skip_validation=True,
        )
        _add_attributes(client, "RunAttribute", run.id, overflow["Run"])
        _add_files(client, row, run_acc)

    return client
