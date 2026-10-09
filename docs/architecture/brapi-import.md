# BrAPI Import

An ingest bridge from any [Breeding API (BrAPI)](https://brapi.org) v2 server
into a validated `miappe`-profile dataset. BrAPI is a standard implemented by
many breeding databases, so the client is **configurable** (base URL plus an
optional bearer token) rather than bound to one endpoint. The importer lives in
`metaseed.brapi` and reuses the ingest seam introduced by the
[ENA importer](ena-import.md).

## What it does

```python
from metaseed.brapi import import_brapi

base = "https://test-server.brapi.org/brapi/v2"
client = import_brapi(base)        # needs the metaseed[brapi] extra
client.validate()                   # report any field gaps
client.serialize()                  # the miappe dataset
```

Given a BrAPI v2 base URL, it fetches studies, observation units, observations,
and germplasm and builds Investigations with their Studies, BiologicalMaterials,
ObservationUnits, ObservedVariables, and DataFile references. Pass
`study_db_id=...` to restrict the import to a single study, or `token=...` for an
authenticated server.

## Choosing a base URL

The base URL is the BrAPI **v2 root**, not the server's home page: it normally ends in `/brapi/v2`. Passing the site root instead is the most common mistake and produces a bare `404`, so the client translates that into a `BrapiEndpointError` naming the missing suffix. A server that answers with an HTML page rather than JSON, or that demands a token, is reported as such instead of as a `JSONDecodeError` or an anonymous failure.

Public servers verified reachable without credentials (checked 260727):

| Server | Base URL |
| --- | --- |
| BrAPI reference server | `https://test-server.brapi.org/brapi/v2` |
| Cassavabase | `https://cassavabase.org/brapi/v2` |
| Sweetpotatobase | `https://sweetpotatobase.org/brapi/v2` |

Breedbase instances such as `wheat.triticeaetoolbox.org` and `musabase.org` implement BrAPI v2 but answer `401` without a token; pass one via `token=`. Not every deployment exposes BrAPI at the same path — Germinate mounts it under the instance path — so check the server's own API documentation when the `/brapi/v2` root does not answer.

## The seam

`base URL → fetch metadata → map (spec-driven) → validate → dataset`, in three
parts:

- **`metaseed.brapi.client.BrapiClient`** — calls the BrAPI v2 `studies`,
  `observationunits`, `observations`, and `germplasm` endpoints. BrAPI wraps
  every payload as `{"metadata": ..., "result": {"data": [...]}}`; each method
  returns the `result.data` list. Sends a descriptive `User-Agent`, adds an
  `Authorization: Bearer <token>` header when a token is given, and accepts an
  injected `httpx.Client` for testing. Requires `httpx` (the `metaseed[brapi]`
  extra).
- **`metaseed.brapi.mapper.build_dataset`** — pure and network-free: maps the
  BrAPI objects into `miappe`-profile entities. Importable without the extra.
- **`metaseed.brapi.import_brapi`** — wires the two together, iterating studies
  to gather their observation units, then each unit's observations.

Observations are collected **per observation unit**, not per study. Servers do
not reliably honour a `studyDbId` filter on `/observations`: the BrAPI reference
server answers it with zero rows even for studies whose observation records
carry that `studyDbId`, so asking that way imported a dataset with no
measurements at all while reporting success. Filtering by `observationUnitDbId`
is honoured, and costs one request per unit already fetched. An observation
returned under more than one unit is imported once, keyed by `observationDbId`.

## BrAPI to MIAPPE mapping

| BrAPI object | MIAPPE entity | Notes |
| --- | --- | --- |
| `studies[].trialDbId` | Investigation | One Investigation per distinct trial; falls back to the `studyDbId` when a study has no trial. |
| `studies[]` | Study | `studyDbId` → `unique_id`, `trialDbId` → `investigation_id`. |
| `germplasm[]` | BiologicalMaterial | `germplasmDbId` → `unique_id`; `study_id` from the germplasm's `studyDbIds[0]`, else the first imported study. |
| `observationunits[]` | ObservationUnit | Position and level fields flattened from `observationUnitPosition` and `observationLevel`. |
| `observations[]` | ObservedVariable | Deduplicated by `observationVariableDbId` (see limitation below). |
| `studies[].dataLinks[]` | DataFile | URL referenced via the `link` field. |

## Design choices

- **Metadata, not raw data.** BrAPI `dataLinks` are *referenced* — each becomes
  a `DataFile` entity carrying its URL — never downloaded.
- **DbIds as `unique_id`.** Each entity's `unique_id` is its BrAPI `DbId`, and
  the `*_id` reference fields hold the parent's `DbId`, so studies, units,
  germplasm, and variables auto-link to their parents.
- **Lenient build.** Entities are created with `skip_validation`, so a record
  that omits a field does not abort the import; `client.validate()` reports gaps
  afterwards, and a reload keeps such an entity rather than dropping it.
- **MIAPPE's vocabularies.** BrAPI carries what a server's database holds. The
  mapper writes the entry type in MIAPPE's spelling where it is one of `test`,
  `check`, `filler`, and the growth facility as the first MIAPPE term the
  server's description contains (`field`, `greenhouse`, `glasshouse`, `growth
  chamber`, `phytotron`, `open top chamber`); what it cannot place is kept as
  sent and reported by validation.
- **Identifiers as the server spells them.** A `DbId` is the server's own key,
  and the `miappe` profiles admit any identifier without whitespace, so it is
  stored unchanged and a round trip through the BrAPI exporter keeps it.
- **Configurable client.** Because BrAPI is a standard, the base URL is required
  and a bearer token is optional, rather than targeting a fixed server.
- **Optional extra.** The network dependency installs only with
  `pip install "metaseed[brapi]"`; importing `metaseed.brapi.mapper` (the pure
  mapper) needs nothing extra, and importing `metaseed.brapi` does not pull in
  the web framework.

## Limitations

- **Observations carry no value entity.** MIAPPE 1.2 has no entity for an
  individual measured value, so BrAPI `observations` are reduced to the distinct
  `ObservedVariable` definitions they reference; the measured `value` and
  `observationDbId` are not retained.
## Export

```python
from metaseed.brapi import to_brapi

bodies = to_brapi(client)
# {"trials": [...], "studies": [...], "observationUnits": [...], "germplasm": [...]}
```

`to_brapi` inverts the importer, rendering a `miappe` dataset as BrAPI v2 JSON
objects — the request bodies a BrAPI server's POST endpoints accept. Pure and
dependency-free. With `import_brapi` this makes metaseed a round-trip BrAPI
bridge.

## What servers actually send

Found by importing from the BrAPI reference server, FAIDARE (INRAE) and a
Breedbase instance (Sweetpotatobase), 261008 and 261009. Each shaped the
importer; none is in the specification.

| Server | What it sends | What the importer does |
|--------|---------------|------------------------|
| All | Ten records per page by default; FAIDARE made a study of 1737 observation units 174 requests | Asks for a thousand per page (`pageSize=1000`), which every server tried honours |
| Reference server | Nothing for `/observations?studyDbId=`, though it holds the observations | Asks per observation unit when the study filter returns nothing |
| FAIDARE | 500 for any `/observations` page past the 20,000th record of a study, whatever the page size | The same fallback: one request per unit, which never reaches that deep |
| FAIDARE | A trial's address (`/trials/<id>`) answered with every study on the server when the importer appended `/studies` to it: 2763 studies | Reads the address first: a trial's imports its studies, a study's that study, anything else below the base URL is refused |
| FAIDARE | `observationLevelRelationships` as one string per unit, `REPLICATE>BLOCK>PLOT:223977,REPLICATE>BLOCK:5,REPLICATE:2`, where the specification has objects; and the level's number in `levelName` with the path of names in `levelOrder` | Reads both forms into level, code, block and replicate |
| FAIDARE | `DbId`s that are base64 and end in `=` | Admitted as identifiers; the `miappe` profiles refused them until 0.60.2 |
| FAIDARE, reference server | A growth facility as a list of CO_715 descriptions, `field environment condition, greenhouse` | Writes the first MIAPPE term it names, `field` |
| Breedbase, reference server | An entry type in capitals, `TEST` | Writes `test` |
| Reference server | A data link whose file name has a dot, `image-archive.zip`, used as the `DataFile` identifier | Admitted; the profiles refused a dot until 0.60.2 |
| Breedbase | The breeding programme's name as the trial's name (`NCSU`), and a study that is a field layout plus measurements: plots, accessions, a few traits | Faithful: that is the record; the dataset is named after the trial |
| All | A dropped connection or a name that did not resolve part way through thousands of requests | Tries a request three times before giving up |

## Testing

The mapper is tested from a hand-written BrAPI fixture; the client is tested with
an `httpx` mock transport (request shape, auth header, and JSON parsing). One
live smoke test against the public `test-server.brapi.org` server is marked
`network` and excluded from the default run.

Those alone proved only self-consistency: the hand-written fixture answers every
request with the same canned payload regardless of query parameters, so an
importer asking the wrong question still got data back. `fixtures/brapi_v2_recorded.json`
closes that gap. It stores the exact `(endpoint, params) -> response` pairs the
reference server returned, including the `studyDbId` query that comes back
empty, and the replaying test answers an unrecorded query the way the server
did — with nothing. That is what makes "an import of a real server produces
measurements" a testable claim, and it is what caught the observation-filter bug
above.

The recording is de-identified on the way in: names, emails, ORCIDs, and
institutions are replaced with synthetic values, while accessions and database
identifiers are kept because the mapper depends on them. A test asserts no real
identity survives. The same replay also covers the BrAPI v2 export shape, so
that conformance check now runs in CI rather than only in the `network` job.
