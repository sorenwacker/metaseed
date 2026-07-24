# MetaboLights Import

An ingest bridge to [MetaboLights](https://www.ebi.ac.uk/metabolights): **import**
public metadata for a study accession into a validated `metabolights`-profile
dataset. It follows the same seam as the [ENA importer](ena-import.md) — the
reference ingest adapter — and lives in `metaseed.metabolights`.

## What it does

```python
from metaseed.metabolights import import_accession

client = import_accession("MTBLS1")   # needs the metaseed[metabolights] extra
client.validate()                      # report any field gaps
client.serialize()                     # the metabolights dataset
```

Given a MetaboLights study accession (e.g. `MTBLS1`), it fetches the study's
metadata document and builds an Investigation with its Contacts, Publications,
and Studies — each Study carrying its Factors, Protocols (and their Parameters),
Samples (and their Characteristics and Factor Values), and Assays (with their
DataFiles and Metabolites).

The Samples, DataFiles and Metabolites are **not** in the ISA-JSON document —
its `samples`/`dataFiles` arrays are empty for every study. They are recovered
from the study's ISA-Tab files (`s_*.txt`, `a_*.txt`, `m_*.tsv`), which
`MetaboLightsClient.study_files` fetches from the study's public download
directory. This requires a **public** study; for an embargoed one the files are
absent and only the ISA-JSON metadata (Investigation/Study/Assay backbone)
imports.

## The seam

`accession → fetch metadata → map (spec-driven) → validate → dataset`, in three
parts:

- **`metaseed.metabolights.client.MetaboLightsClient`** — calls the MetaboLights
  web service `studies/{accession}` endpoint and returns the parsed metadata
  document. Sends a descriptive `User-Agent` (EBI etiquette) and accepts an
  injected `httpx.Client` for testing. Requires `httpx` (the
  `metaseed[metabolights]` extra).
- **`metaseed.metabolights.mapper.build_dataset`** — pure and network-free: maps
  the document into `metabolights`-profile entities. Importable without the extra.
- **`metaseed.metabolights.import_accession`** — wires the two together.

## The source document

The MetaboLights web service exposes each study in the ISA model. The importer
reads the `isaInvestigation` object: its `people`, `publications`, and `studies`,
and within each study the `studyDesignDescriptors`, `factors`, `protocols`,
`samples`, and `assays`. ISA ontology annotations (dicts carrying
`annotationValue`) are flattened to their label; an organism is read from the
sample characteristic named `Organism`. The `organism_term` field is left unset:
it is typed as an `ontology_term`, whose coercion resolves the value against OLS4
and would make the otherwise network-free mapper issue a request per sample.

## Design choices

- **Metadata, not raw data.** Spectra are *referenced* — each assay data file
  becomes a `DataFile` entity whose `filename` is a resolvable URL under the
  study's public download root (`studyHttpUrl`, falling back to `studyFtpUrl`) —
  never downloaded.
- **Hierarchy via `parent_id`.** Entities are linked to their parents
  (Investigation → Study → {Factor, Protocol, Sample, Assay}, …) so the dataset
  mirrors the profile's parent-child structure.
- **Lenient build.** Entities are created with `skip_validation`, so a record
  that omits a field — or carries a free-text value outside a profile enum — does
  not abort the import; `client.validate()` reports gaps afterwards.
- **Optional extra.** The network dependency installs only with
  `pip install "metaseed[metabolights]"`; importing
  `metaseed.metabolights.mapper` (the pure mapper) needs nothing extra, and
  importing `metaseed.metabolights` does not pull in the web framework.

## Export

```python
from metaseed.metabolights import to_metabolights

docs = to_metabolights(client)   # {"i_Investigation.txt": ..., "m_*.tsv": ..., ...}
```

`to_metabolights` renders a `metabolights` dataset as the MetaboLights archive:
the ISA-Tab documents (via `metaseed.isatab.to_isatab`) plus one **Metabolite
Assignment File** (`m_*.tsv`) per Assay. Each MAF is the standard MAF column
header followed by **one row per `Assay.metabolites` entry**; the MAF column
names match the `Metabolite` entity field names, so each column is a direct
lookup (columns the profile does not model — e.g. `search_engine`, `taxid` —
stay empty). An assay with no metabolites yields a valid header-only MAF. Pure
and dependency-free.

Note: the *importer* does not populate metabolites (see Limitations), so a
populated MAF comes from datasets authored in metaseed or loaded with
`Assay.metabolites` present.

## CV-term compliance

```python
from metaseed.metabolights import validate_cv

issues = validate_cv(client)   # [] when every CV accession resolves
```

`validate_cv` collects the dataset's controlled-vocabulary accessions — each
sample's `organism_term` and each identified metabolite's `database_identifier`
(e.g. a ChEBI id) — and resolves them against OLS4 via the shared
`OntologyService`, returning a `ValidationError` (rule `cv_compliance`) per
accession that does not exist. A transient OLS4 outage fails open. Pass
`service=` to inject a stub in tests.

## Limitations

- **Public studies only for sample/metabolite data.** The Sample, DataFile and
  Metabolite tables come from the study's ISA-Tab files on the public FTP
  download root. An embargoed or otherwise non-public study exposes no such
  files, so it imports the ISA-JSON backbone (Investigation/Study/Assay,
  Contacts, Publications, Factors, Protocols) but no Samples, DataFiles, or
  Metabolites.
- **Free-text vs. enum values.** MetaboLights annotation values (e.g.
  `technology_type`, `measurement_type`) are recorded verbatim and may fall
  outside the profile's enumerations; `validate()` surfaces these.

## Future option

A later version may delegate fetching and table parsing to the official
[`metabolights-utils`](https://pypi.org/project/metabolights-utils/) library to
add per-sample rows and metabolite assignments. This first version is
`httpx`-only to match the ENA importer and keep the dependency surface minimal.

## Testing

The mapper is tested from a recorded study fixture; the client is tested with an
`httpx` mock transport (request shape + JSON parsing). One live smoke test
against the real MetaboLights API (accession `MTBLS1`) is marked `network` and
excluded from the default run.
