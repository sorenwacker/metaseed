"""Every column ENA publishes for a run must reach the dataset.

The adapter requests ``fields=all``, so a row carries every ``read_run`` column.
A column with a declared ``ena``-profile field fills that field; a column without
one becomes an attribute on the entity ENA says owns it. Nothing published is
dropped, and nothing is recorded twice.

The column lists are recorded from ENA's own ``returnFields`` endpoint, so these
tests describe ENA's schema rather than the mapper's opinion of it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaseed.ena.mapper import build_dataset

FIXTURES = Path(__file__).parent / "fixtures"
RUN_COLUMNS: list[str] = json.loads((FIXTURES / "read_run_columns.json").read_text())
SAMPLE_COLUMNS: set[str] = set(
    json.loads((FIXTURES / "sample_columns.json").read_text())
)

# The file manifests are ";"-separated parallel lists consumed into File
# entities, so their joined values never appear verbatim in the dataset. They
# are checked separately, by filename and checksum.
FILE_MANIFEST_COLUMNS = {
    "fastq_ftp",
    "fastq_md5",
    "submitted_ftp",
    "submitted_md5",
    "sra_ftp",
    "sra_md5",
    "bam_ftp",
    "bam_md5",
}

# Columns whose declared field is not a string; a marker value would not survive
# coercion, so they get values of the right shape, spelled as the declared type
# serializes them.
TYPED_COLUMN_VALUES = {
    "tax_id": "4577",
    "lat": "48.8566",
    "lon": "2.3522",
    "environmental_sample": "True",
    "nominal_length": "300",
    "nominal_sdev": "50.0",
}


def _row(**overrides: Any) -> dict[str, Any]:
    """A run row with every ENA column filled with a distinguishable value."""
    row = {c: TYPED_COLUMN_VALUES.get(c, f"value-of-{c}") for c in RUN_COLUMNS}
    row.update(
        {
            "study_accession": "PRJEB10000",
            "sample_accession": "SAMEA001",
            "experiment_accession": "ERX001",
            "run_accession": "ERR001",
            "fastq_ftp": "ftp.x/ERR001_1.fastq.gz;ftp.x/ERR001_2.fastq.gz",
            "fastq_md5": "aaa111;bbb222",
        }
    )
    row.update(overrides)
    return row


def _entities(client) -> list[dict]:
    return client.serialize()["entities"]


def _by_type(client, entity_type: str) -> list[dict]:
    return [e for e in _entities(client) if e["_type"] == entity_type]


def _attributes(client, entity_type: str) -> dict[str, str]:
    return {a["tag"]: a["value"] for a in _by_type(client, entity_type)}


def _recorded_values(client) -> set[str]:
    """Every scalar value present anywhere in the dataset, as a string."""
    values: set[str] = set()
    for entity in _entities(client):
        for key, value in entity.items():
            if key.startswith("_") or value is None:
                continue
            values.add(str(value))
    return values


def test_every_non_empty_column_reaches_the_dataset():
    """The completeness rule itself: no published column is silently dropped."""
    row = _row()
    recorded = _recorded_values(build_dataset([row]))

    missing = sorted(
        column
        for column, value in row.items()
        if value and column not in FILE_MANIFEST_COLUMNS and str(value) not in recorded
    )
    assert missing == []


def test_every_non_empty_column_of_a_real_ena_response_reaches_the_dataset():
    """The same rule against a recorded PRJNA273563 response (45 filled columns)."""
    rows = json.loads((FIXTURES / "read_run_all_fields.json").read_text())
    recorded = _recorded_values(build_dataset(rows))

    missing = sorted(
        column
        for column, value in rows[0].items()
        if value and column not in FILE_MANIFEST_COLUMNS and str(value) not in recorded
    )
    assert missing == []


def test_declared_sample_fields_are_filled_from_the_run_report():
    """The fields issue #271 reported as unreachable are reachable in one call."""
    rows = json.loads((FIXTURES / "read_run_all_fields.json").read_text())
    sample = _by_type(build_dataset(rows), "Sample")[0]

    assert sample["ecotype"] == "88"
    assert sample["geographic_location_country"] == "France"
    assert sample["tissue_type"] == "leaf"
    assert sample["center_name"] == "Example Institute of Plant Research"
    assert sample["description"] == "Plant sample from Arabidopsis thaliana"
    assert sample["scientific_name"] == "Arabidopsis thaliana"


def test_a_column_becomes_an_attribute_on_the_entity_ena_says_owns_it():
    client = build_dataset([_row()])

    assert _attributes(client, "SampleAttribute")["tax_lineage"] == (
        "value-of-tax_lineage"
    )
    assert _attributes(client, "ExperimentAttribute")["library_gen_protocol"] == (
        "value-of-library_gen_protocol"
    )
    assert _attributes(client, "RunAttribute")["read_count"] == "value-of-read_count"


def test_a_column_with_no_declared_field_lands_where_ena_puts_it():
    """Sample-owned columns become sample attributes, and only those."""
    client = build_dataset([_row()])
    sample_tags = set(_attributes(client, "SampleAttribute"))

    assert sample_tags <= SAMPLE_COLUMNS
    assert not sample_tags & set(_attributes(client, "ExperimentAttribute"))
    assert not sample_tags & set(_attributes(client, "RunAttribute"))


def test_an_unrecognised_column_is_carried_as_a_run_attribute():
    """A column ENA adds after this release is carried, not discarded."""
    client = build_dataset([_row(some_future_ena_column="42")])

    assert _attributes(client, "RunAttribute")["some_future_ena_column"] == "42"


def test_a_column_with_a_declared_field_is_never_also_an_attribute():
    """A declared field wins, so the same fact never appears twice."""
    client = build_dataset([_row()])
    tags = (
        set(_attributes(client, "SampleAttribute"))
        | set(_attributes(client, "ExperimentAttribute"))
        | set(_attributes(client, "RunAttribute"))
    )

    assert not tags & {"ecotype", "country", "tissue_type", "tax_id", "collection_date"}
    assert not tags & {"library_strategy", "instrument_model", "run_accession"}


def test_empty_columns_are_absences_not_attributes():
    client = build_dataset([_row(ecotype="", tax_lineage="", read_count="")])
    sample = _by_type(client, "Sample")[0]

    assert "ecotype" not in sample
    assert "tax_lineage" not in _attributes(client, "SampleAttribute")
    assert "read_count" not in _attributes(client, "RunAttribute")


def test_attributes_are_written_once_per_entity_not_once_per_run():
    """Two runs of one experiment share a sample; its attributes are not doubled."""
    rows = [_row(), _row(run_accession="ERR002", fastq_ftp="ftp.x/b.fastq.gz")]
    client = build_dataset(rows)

    lineages = [
        a for a in _by_type(client, "SampleAttribute") if a["tag"] == "tax_lineage"
    ]
    assert len(lineages) == 1


def test_every_published_file_set_becomes_file_entities():
    """A run submitted as BAM is not reduced to its derived FASTQ."""
    client = build_dataset(
        [
            _row(
                fastq_ftp="ftp.x/ERR001.fastq.gz",
                fastq_md5="aaa",
                submitted_ftp="ftp.x/ERR001.bam",
                submitted_md5="bbb",
                submitted_format="BAM",
                sra_ftp="ftp.x/ERR001.sra",
                sra_md5="ccc",
                bam_ftp="ftp.x/ERR001.aln.bam",
                bam_md5="ddd",
            )
        ]
    )
    files = {f["filename"]: f for f in _by_type(client, "File")}

    assert set(files) == {
        "ERR001.fastq.gz",
        "ERR001.bam",
        "ERR001.sra",
        "ERR001.aln.bam",
    }
    assert files["ERR001.bam"]["checksum"] == "bbb"
    # ENA reports "BAM"; the SRA schema enumerates "bam".
    assert files["ERR001.bam"]["filetype"] == "bam"
    assert all(f["run_ref"] == "ERR001" for f in files.values())


def test_the_submitted_file_type_is_spelled_as_the_sra_schema_spells_it():
    """ENA reports "SFF"; the SRA schema enumerates "sff" and rejects "SFF"."""
    client = build_dataset(
        [_row(submitted_ftp="ftp.x/a.sff", submitted_md5="aaa", submitted_format="SFF")]
    )
    files = {f["filename"]: f for f in _by_type(client, "File")}

    assert files["a.sff"]["filetype"] == "sff"


def test_an_instrument_native_file_type_keeps_its_capitalisation():
    """The schema's enumeration is not uniformly lower case, so lowercasing
    every reported format would be rejected just as readily."""
    client = build_dataset(
        [
            _row(
                submitted_ftp="ftp.x/a.h5",
                submitted_md5="aaa",
                submitted_format="pacbio_hdf5",
            )
        ]
    )
    files = {f["filename"]: f for f in _by_type(client, "File")}

    assert files["a.h5"]["filetype"] == "PacBio_HDF5"


def test_a_missing_submitted_format_is_read_off_the_filename():
    client = build_dataset(
        [
            _row(
                submitted_ftp="ftp.x/a.cram.gz",
                submitted_md5="aaa",
                submitted_format="",
            )
        ]
    )
    files = {f["filename"]: f for f in _by_type(client, "File")}

    assert files["a.cram.gz"]["filetype"] == "cram"  # past the compression suffix


def test_an_unrecognised_submitted_format_is_passed_through_not_guessed():
    client = build_dataset(
        [
            _row(
                submitted_ftp="ftp.x/a.xyz",
                submitted_md5="aaa",
                submitted_format="SomeNewFormat",
            )
        ]
    )
    files = {f["filename"]: f for f in _by_type(client, "File")}

    assert files["a.xyz"]["filetype"] == "SomeNewFormat"
