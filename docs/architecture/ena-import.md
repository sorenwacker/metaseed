# ENA Integration

A round-trip bridge to the [European Nucleotide Archive](https://www.ebi.ac.uk/ena):
**import** public metadata into a validated `ena`-profile dataset, and **export**
a dataset back to ENA submission XML. The importer is the reference ingest
adapter (the seam BrAPI/PRIDE/MetaboLights importers reuse); the exporter is the
round-trip partner. Both live in `metaseed.ena`.

## What it does

```python
from metaseed.ena import import_accession

client = import_accession("PRJEB10000")   # needs the metaseed[ena] extra
client.validate()                          # report any field gaps
client.serialize()                         # the ena dataset
```

Given an ENA accession (study, sample, experiment, or run), it fetches the
run-level metadata and builds a Study with its Samples, Experiments, Runs, and
File references.

## The seam

`accession → fetch metadata → map (spec-driven) → validate → dataset`, in three
parts:

- **`metaseed.ena.client.EnaClient`** — calls the ENA Portal `filereport`
  endpoint (`result=read_run`) and returns one record per run. Sends a
  descriptive `User-Agent` (EBI etiquette) and accepts an injected `httpx.Client`
  for testing. Requires `httpx` (the `metaseed[ena]` extra).
- **`metaseed.ena.mapper.build_dataset`** — pure and network-free: maps the rows
  into `ena`-profile entities. Importable without the extra.
- **`metaseed.ena.import_accession`** — wires the two together.

## Design choices

- **Metadata, not raw data.** FASTQ files are *referenced* — each becomes a
  `File` entity carrying its name and MD5 checksum — never downloaded.
- **Accessions as `alias`.** Each entity's `alias` is its accession, and the
  `*_ref` fields hold the parent's accession, so samples/experiments/runs/files
  auto-link to their parents.
- **Lenient build.** Entities are created with `skip_validation`, so a record
  that omits a field does not abort the import; `client.validate()` reports gaps
  afterwards.
- **Optional extra.** The network dependency installs only with
  `pip install "metaseed[ena]"`; importing `metaseed.ena.mapper` (the pure
  mapper) needs nothing extra, and importing `metaseed.ena` does not pull in the
  web framework.

## Export (round-trip)

```python
from metaseed.ena import to_ena_xml

docs = to_ena_xml(client)        # {"study.xml": ..., "sample.xml": ..., ...}
```

`to_ena_xml` renders an `ena`-profile dataset as the ENA/SRA submission
documents — `STUDY_SET`, `SAMPLE_SET`, `EXPERIMENT_SET`, `RUN_SET`. It is pure
and dependency-free (stdlib `xml.etree`); data files are *referenced* in
`RUN > DATA_BLOCK > FILES`, never uploaded (submission/auth is out of scope). So
`import_accession` and `to_ena_xml` round-trip through the same profile.

## Testing

The mapper is tested from a recorded `read_run` fixture; the client is tested
with an `httpx` mock transport (request shape + JSON parsing); the exporter is
tested by parsing its output back with `xml.etree`. One live smoke test against
the real ENA API is marked `network` and excluded from the default run.
