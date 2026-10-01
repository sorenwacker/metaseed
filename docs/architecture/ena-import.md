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

Given an ENA accession (study, sample, experiment, or run), it fetches every
column ENA publishes for the study, its runs and its analyses — three requests,
never one per record — and builds a Study with its Samples, Experiments, Runs,
Analyses and File references.

## Completeness

The Portal publishes a study under three results, and the `ena` profile
describes all three, so the import asks for all three with `fields=all`:

| Portal result | Rows | Becomes |
| --- | --- | --- |
| `result=study` | one, the study record | the Study's `description` and `center_name`, and a `StudyAttribute` per remaining column (`study_name`, `keywords`, `breed`, `tax_division`, `geo_accession`, `parent_study_accession`, `secondary_study_alias`, `secondary_study_center_name`, ...) |
| `result=read_run` | one per run, all ~196 columns | Sample, Experiment, Run, File and their attributes |
| `result=analysis` | one per analysis (assembly, variant call, annotation, ...) | Analysis, its File references and `AnalysisAttribute`s; a Sample the runs did not already carry |

Three requests per import, whatever the study's size: one accession never
becomes N requests. A study with no analyses is answered by the Portal with an
empty list, which the import records as no Analysis entities; `import_accession`
logs the three counts so an empty answer is visibly an answer, not a query that
was never made.

Every non-empty column of every row then reaches the dataset:

- a column with a declared field in the `ena` profile fills that field;
- a column without one becomes an attribute (`StudyAttribute`,
  `SampleAttribute`, `ExperimentAttribute`, `RunAttribute` or
  `AnalysisAttribute`) whose `tag` is the ENA column name and whose `value` is
  ENA's value verbatim;
- an empty column is an absence, not a value, and is skipped;
- a fact is recorded once: a column the study row already supplied is not
  written again from a run or an analysis row.

Which entity owns a column is ENA's answer rather than metaseed's: the columns
ENA lists only under `result=study` belong to the Study, the columns it lists
under `result=sample` belong to the Sample, an explicit set of library and
sequencing descriptors belongs to the Experiment, and everything else belongs to
the row's own subject — the Run for a run row, the Analysis for an analysis row.
That subject is the catch-all, so a column ENA adds after this release is carried
as an attribute rather than dropped.

Of the 37 fields the `ena` profile declares on `Sample`, 34 have a `read_run`
column and are filled when ENA publishes them. Measured against **PRJNA273563**
(1001 Genomes, 1,135 samples), `Sample` field completeness rises from 16% to 30%
— `ecotype`, `geographic_location_country`, `tissue_type`, `center_name` and
`description` all arrive in the same response that carries the run — and the
import additionally records 11,350 sample attributes, 12,485 run attributes and
1,135 experiment attributes for the columns the profile declares no field for.

Four file sets are published per run — `fastq`, `submitted`, `sra` and `bam` —
and each becomes `File` entities, so a run whose data was submitted as BAM or
CRAM is not reduced to its derived FASTQ. The Portal reports a submitted file's
format in upper case (`SFF`, `BAM`), which the SRA schema's enumeration rejects,
so the format is written back in the schema's own spelling (`sff`, `bam`, and
`PacBio_HDF5` — the enumeration is not uniformly lower case). A format the
schema does not list is passed through unchanged rather than replaced by a
guess, and one that cannot be read at all is left unset for `validate()` to
report.

The Portal reports every column as a string, so the six declared fields the
profile does not type as a string are coerced on the way in: `taxon_id` and
`insert_size` to integer, `insert_size_stddev` and the two `lat_lon` components
to float, `environmental_sample` to boolean, and `run_date` to a date. ENA
writes a run date either as `YYYY-MM-DD` or with a time part
(`2010-02-01T00:00:00`); both are read, and the time is dropped because the
profile declares a date. A value that cannot be read is left unset rather than
written in the wrong type — a string in a date field survives the mapper but
fails on export, where the SRA schema types the element.

### What the Portal does not publish

Three declared `Sample` fields — `common_name`, `geographic_location_region`
and `lab_host` — have no column under any Portal result (`read_run`, `sample`,
`study` or `analysis`; the column lists are recorded from ENA's `returnFields`
endpoint in `tests/test_ena/fixtures/`). An import leaves them empty; they are
there for datasets written by hand or exported to ENA, where the SRA schema
accepts them as sample attributes.

## The seam

`accession → fetch metadata → map (spec-driven) → validate → dataset`, in three
parts:

- **`metaseed.ena.client.EnaClient`** — calls the ENA Portal `filereport`
  endpoint once per result (`study`, `read_run`, `analysis`, each with
  `fields=all`) and returns the rows, each carrying every column ENA publishes.
  Sends a descriptive `User-Agent` (EBI etiquette) and accepts an injected
  `httpx.Client` for testing. Requires `httpx` (the `metaseed[ena]` extra).
- **`metaseed.ena.mapper.build_dataset`** — pure and network-free: takes the
  three row sets and routes each column of each row to a declared `ena`-profile
  field, or to an attribute on the entity ENA says owns that column. Importable
  without the extra.
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
- **Attributes as the overflow, not as a dumping ground.** A column is written as
  an attribute only when the profile declares no field for it. A declared field
  always wins, so the same fact never appears twice.
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
| `study.xml` | `STUDY_SET` | Study, with `STUDY_LINKS` from its ProjectLinks and `STUDY_ATTRIBUTES` from its StudyAttributes |
| `sample.xml` | `SAMPLE_SET` | Sample, with `SAMPLE_ATTRIBUTES` from its SampleAttributes |
| `experiment.xml` | `EXPERIMENT_SET` | Experiment, with `EXPERIMENT_ATTRIBUTES` |
| `run.xml` | `RUN_SET` | Run, its Files, and `RUN_ATTRIBUTES` |
| `analysis.xml` | `ANALYSIS_SET` | Analysis, its Files, and `ANALYSIS_ATTRIBUTES` |
| `submission.xml` | `SUBMISSION` | One `ADD` action per document above, plus `HOLD` when the study sets a release date |

Only documents with content are emitted.

**Every entity the profile defines is exported.** The attribute objects
(`StudyAttribute`, `SampleAttribute`, `ExperimentAttribute`, `RunAttribute`,
`AnalysisAttribute`)
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
marked secret: the Plugins page never sends a stored secret to the browser, shows `********` in its empty field to say one is stored, and keeps it when the field is left blank. They are stored by the shared
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

The mapper is tested from recorded `study`, `read_run` and `analysis` fixtures
(PRJEB29581, a metagenome study with assemblies, for the latter two); the client
is tested with an `httpx` mock transport (request shape + JSON parsing); the
exporter is tested by parsing its output back with `xml.etree`. One test asserts
the completeness rule directly for run rows and for analysis rows — every
non-empty column reaches the dataset, as a field or as an attribute — so a column
added to a fixture cannot be silently ignored. One round-trip test imports the
fixtures and exports them, and fails if an analysis does not come out in
`analysis.xml`: the exporter could emit a document the importer never produced,
and nothing said so. One live smoke test against the real ENA API is marked
`network` and excluded from the default run.
