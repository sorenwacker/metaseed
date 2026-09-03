# PRIDE Import

An ingest bridge to the [PRIDE Archive](https://www.ebi.ac.uk/pride): **import**
public proteomics metadata for a ProteomeXchange accession into a validated
`pride`-profile dataset. It follows the same seam as the
[ENA importer](ena-import.md) (the reference ingest adapter). It lives in
`metaseed.pride`.

## What it does

```python
from metaseed.pride import import_accession

client = import_accession("PXD000001")   # needs the metaseed[pride] extra
client.validate()                          # report any field gaps
client.serialize()                         # the pride dataset
```

Given a ProteomeXchange accession, it fetches the project metadata and file list
from the PRIDE Archive `v2` web service and builds a single `Dataset` carrying
its nested Species, Instruments, Modifications, Contacts, Publications, Samples,
and referenced DataFiles.

## The seam

`accession → fetch metadata → map (spec-driven) → validate → dataset`, in three
parts:

- **`metaseed.pride.client.PrideClient`** — calls the PRIDE Archive `v2`
  endpoints `GET /projects/{accession}` (project metadata) and
  `GET /projects/{accession}/files` (file list, unwrapping the HAL paged
  `{"_embedded": {"files": [...]}}` shape when present). Sends a descriptive
  `User-Agent` (EBI etiquette) and accepts an injected `httpx.Client` for
  testing. Requires `httpx` (the `metaseed[pride]` extra).
- **`metaseed.pride.mapper.build_dataset`** — pure and network-free: maps the
  project record plus file list into `pride`-profile entities. Importable
  without the extra.
- **`metaseed.pride.import_accession`** — wires the two together.

## Mapping

The `pride` profile is *composed*: a single root `Dataset` holds the other
entity types as nested lists.

| PRIDE source field | pride target |
| --- | --- |
| `accession` | `Dataset.identifier`, `Dataset.accession` |
| `title`, `projectDescription` | `Dataset.title`, `Dataset.description` |
| `sampleProcessingProtocol`, `dataProcessingProtocol` | the matching `Dataset` protocol fields |
| `submissionType`, `publicationDate`, `keywords` | `Dataset.submission_type`, `announcement_date`, `keywords` |
| `organisms[]` | `Dataset.species[]` and synthesized `Dataset.samples[]` |
| `instruments[]` | `Dataset.instruments[]` (CV accession + name) |
| `identifiedPTMStrings[]` | `Dataset.modifications[]` |
| `submitters[]`, `labPIs[]` | `Dataset.contacts[]` (roles `submitter` / `lab head`) |
| `references[]` | `Dataset.publications[]` |
| files list | `Dataset.files[]` (DataFile references) |

## Design choices

- **Metadata, not raw data.** RAW/mzML/peak-list files are *referenced* — each
  becomes a `DataFile` entity carrying its name, type, format, size, and
  checksum — never downloaded.
- **Composed dataset.** PRIDE describes one project; the import produces a single
  `Dataset` with the related records nested in its list fields, rather than a
  graph of cross-referenced entities.
- **Samples synthesized from organisms.** The project endpoint does not expose
  individual biological samples, so one `Sample` is derived per organism,
  enriched with the project's first organism part and disease when present.
- **Lenient build.** The `Dataset` is created with `skip_validation`, so a
  project that omits a field does not abort the import; `client.validate()`
  reports gaps (including the profile's `min_items` rules) afterwards. Empty
  values are dropped so missing fields are absent, not blank.
- **Optional extra.** The network dependency installs only with
  `pip install "metaseed[pride]"`; importing `metaseed.pride.mapper` (the pure
  mapper) needs nothing extra, and importing `metaseed.pride` does not pull in
  the web framework.

## Export

```python
from metaseed.pride import to_pride_bundle, to_pride_sdrf, to_pride_submission

docs = to_pride_submission(client)   # {"submission.px": ...}
sdrf = to_pride_sdrf(client)         # {"sdrf.tsv": ...}
both = to_pride_bundle(client)       # {"submission.px": ..., "sdrf.tsv": ...}
```

`to_pride_submission` renders a `pride` dataset as the PRIDE px-submission
`submission.px` file: `MTD` metadata lines (project title, submitters, species,
instruments, modifications, and the publication's `pubmed_id`/`doi`) and one
`FME` entry per referenced file.

The file is **line-based**: one record per line, and the format has no
continuation syntax. A value containing a newline would therefore split into a
second line that is not a valid record, so whitespace inside a value is
collapsed to single spaces before it is written. Descriptions and abstracts
routinely contain newlines, so this is the ordinary case rather than an edge
one.

`to_pride_sdrf` renders the [SDRF-Proteomics](https://github.com/bigbio/proteomics-sample-metadata)
sample-to-data table: one row per `(sample, data file)` pair. The columns follow
the order the specification sets out — sample metadata, then data-file metadata
— and every column the specification marks REQUIRED is present:

| Column | Source |
| --- | --- |
| `source name` | `Sample.name` |
| `characteristics[organism]`, `[organism part]`, `[cell type]`, `[disease]` | the Sample, plus any custom attributes |
| `characteristics[biological replicate]` | `1` — the value the specification gives when there are no replicates |
| `assay name`, `technology type` | derived per row |
| `comment[proteomics data acquisition method]` | not modelled → `not available` |
| `comment[label]` | not modelled → `not available` |
| `comment[instrument]` | `Instrument.name` |
| `comment[cleavage agent details]` | not modelled → `not available` |
| `comment[fraction identifier]` | `1` — the specification's value for unfractionated |
| `comment[technical replicate]` | `1` — the specification's value for no replicates |
| `comment[data file]` | `DataFile.filename` |

A column the profile does not model is written as `not available`, which the
specification names as the value for a mandatory column whose content is
unknown. Omitting the column instead would fail validation, so the column is
always present. No `factor value[...]` column is written: the profile models no
study variable, and naming one would invent the experiment's design.

Files link to samples via `DataFile.sample_refs`. Returns `{}` when the dataset
has no samples.

`to_pride_bundle` returns both documents in one mapping. A ProteomeXchange
submission needs the `submission.px` and its SDRF table together, so this is the
form the adapter registry declares (action key `pride`) and the form hosts offer
as a single download: one archive holding both files. The SDRF is omitted when
the dataset has no samples, rather than shipping a header-only table.

All three are pure and dependency-free. With `import_accession` this makes
metaseed a round-trip PRIDE bridge.

## Registry actions

The adapter registry (`metaseed.adapters`) declares what a host application
offers for a `pride` dataset:

| Action key | Kind | Surface | Target |
| --- | --- | --- | --- |
| `pride` | export | `export-menu` | `to_pride_bundle` — `submission.px` + `sdrf.tsv` |
| `pride-import` | import | `import-menu` | `import_accession` — fetch a PXD accession |

The export is one action rather than two because the two documents are parts of
one submission, not alternatives; splitting them into separate controls made a
host render two buttons for one deliverable.

## CV-term compliance

```python
from metaseed.pride import validate_cv

issues = validate_cv(client)   # [] when every CV accession resolves
```

`validate_cv` collects the dataset's controlled-vocabulary accessions —
instrument and modification `cv_accession`, sample `tissue_accession`, and
custom-attribute `cv_accession` — and resolves each against OLS4 via the shared
`OntologyService`, returning a `ValidationError` (rule `cv_compliance`) per
accession that does not exist. A transient OLS4 outage fails open (nothing
flagged). Pass `service=` to inject a stub in tests.

## PX submission structure

```python
from metaseed.pride import validate_submission

issues = validate_submission(client)   # [] when the submission.px is compliant
```

`validate_submission` applies the ProteomeXchange submission-file rules to the
`submission.px` produced by `to_pride_submission` — without invoking the Java
`px-submission-tool`, it encodes the same rules: mandatory `MTD` fields present
(submitter, lab head, project, keywords, `submission_type`, `experiment_type`,
`species`, `tissue`, `instrument`), `submission_type` one of COMPLETE/PARTIAL,
`reason_for_partial` present for PARTIAL, and a well-formed file mapping (at least
one RAW file, valid file types, and a RESULT (COMPLETE) or SEARCH (PARTIAL)
file). Each violation is a `ValidationError` with rule `px_structure`.

## Testing

The mapper is tested from recorded `project` and `files` fixtures; the client is
tested with an `httpx` mock transport. The exporters and `validate_submission`
are tested against real generated documents (no network). CV resolution is
two-tier: hermetic dev tests (stubbed service and pure collection checks) run in
CI, and `network`-marked tests resolve real accessions against live OLS4 before
releases. Live-API smoke tests are `network`-marked and excluded from the default
run.
