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
documents. It is pure and dependency-free (stdlib `xml.etree`); data files are
*referenced* in `RUN > DATA_BLOCK > FILES`, never uploaded (transferring the
files and authenticating to Webin are out of scope).

| Document | ENA set | Built from |
| --- | --- | --- |
| `study.xml` | `STUDY_SET` | Study, with `STUDY_LINKS` from its ProjectLinks |
| `sample.xml` | `SAMPLE_SET` | Sample, with `SAMPLE_ATTRIBUTES` from its SampleAttributes |
| `experiment.xml` | `EXPERIMENT_SET` | Experiment, with `EXPERIMENT_ATTRIBUTES` |
| `run.xml` | `RUN_SET` | Run, its Files, and `RUN_ATTRIBUTES` |
| `analysis.xml` | `ANALYSIS_SET` | Analysis, its Files, and `ANALYSIS_ATTRIBUTES` |
| `submission.xml` | `SUBMISSION` | One `ADD` action per document above, plus `HOLD` when the study sets a release date |

Only documents with content are emitted.

**Every entity the profile defines is exported.** The attribute objects
(`SampleAttribute`, `ExperimentAttribute`, `RunAttribute`, `AnalysisAttribute`)
each carry a `tag`, a `value` and an optional `units`, and become the
`TAG`/`VALUE`/`UNITS` of an attribute under the object that owns them. This
matters beyond fidelity: ENA registers samples against a *checklist*, and a
checklist's mandatory fields (collection date, geographic location, and so on)
are carried as sample attributes — a `SAMPLE_SET` without them is rejected. An
exporter that drops them produces a file that looks complete and cannot be
submitted, which is why `tests/test_ena/test_export_loses_nothing.py` fails if
any entity type present in a dataset does not reach the XML.

Attributes are found through the containment the profile declares
(`Sample.sample_attributes`, `Run.run_attributes`, …), so the exporter walks the
entity tree rather than grouping a flat entity list by type — a flat grouping
cannot say which sample an attribute belongs to. `File` is nested under both
`Run` and `Analysis`, so a file follows its parent.

`import_accession` and `to_ena_xml` therefore round-trip through the same
profile: what the importer builds, the exporter emits.

## Webin credentials

Submitting to ENA needs a Webin account, so the `ena` adapter declares two
settings — `webin_username` (the `Webin-NNNNN` account) and `webin_password`,
marked secret so the Plugins page masks it. They are stored by the shared
settings layer, in `settings.json` written with owner-only permissions.

```python
from metaseed.ena.connection import check_connection

check_connection({"webin_username": "Webin-12345", "webin_password": "..."})
# ConnectionCheck(ok=True, message="ENA accepted Webin-12345 on the test service.")
```

The check posts the credentials to ENA's Webin authentication endpoint, which
returns a token for a valid account and `401` for anything else. It uses ENA's
**test** service: the account is the same one production uses, so a token from
the test service proves the credentials, and confirming a password never
touches the live archive. A submission chooses its service separately and
deliberately.

An outage is reported as an outage rather than as a rejected password — someone
else's downtime must not read as a wrong credential.

Storing credentials on a **hub** is a different problem, because a hub holds
other people's: there they are encrypted at rest rather than kept in a file.

## Testing

The mapper is tested from a recorded `read_run` fixture; the client is tested
with an `httpx` mock transport (request shape + JSON parsing); the exporter is
tested by parsing its output back with `xml.etree`. One live smoke test against
the real ENA API is marked `network` and excluded from the default run.
