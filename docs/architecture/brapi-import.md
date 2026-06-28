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
  to gather their observation units and observations.

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
  afterwards.
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
- **Single-page fetch.** Each endpoint is read once; BrAPI pagination beyond the
  server's default page is not followed.

## Testing

The mapper is tested from a recorded BrAPI fixture; the client is tested with an
`httpx` mock transport (request shape, auth header, and JSON parsing). One live
smoke test against the public `test-server.brapi.org` server is marked `network`
and excluded from the default run.
