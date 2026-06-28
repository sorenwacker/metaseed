# ENA Import

Imports public metadata from the [European Nucleotide Archive](https://www.ebi.ac.uk/ena)
into a validated `ena`-profile dataset. It is the reference **importer** — the
mirror image of the exporters (e.g. [DCAT](dcat.md)) — and establishes the seam
the other repository importers (BrAPI, PRIDE, MetaboLights) reuse.

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

## Testing

The mapper is tested from a recorded `read_run` fixture; the client is tested
with an `httpx` mock transport (request shape + JSON parsing). One live smoke
test against the real ENA API is marked `network` and excluded from the default
run.
