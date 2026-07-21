# SEEK Export

Export a metaseed ISA dataset to [FAIRDOM-SEEK](https://seek4science.org/). SEEK
ingests the output with its **own built-in** "Import from FAIR Data Station"
feature — metaseed generates the RDF directly; **no external FAIR Data Station
tool is involved.**

```python
from metaseed.seek import to_fair_data_station_rdf

turtle = to_fair_data_station_rdf(client)   # needs metaseed[seek]
```

`to_fair_data_station_rdf` renders any **ISA-shaped** metaseed dataset
(Investigation → Study → Assay/Sample) as a Turtle RDF document. It uses
`rdflib` (the `metaseed[seek]` extra), and mirrors the format SEEK's reader
(`lib/seek/fair_data_station/`) expects:

- **instances** — one resource per entity, typed `jerm:Investigation`/`Study`/
  `Assay`/`Sample`, linked by `jerm:hasPart`, with `schema:identifier`/`name`/
  `title`/`description` and one triple per populated field;
- **property definitions** — each field property declared `rdf:Property` with
  `rdfs:label`, `schema:description`, `schema:valuePattern` (from the field's
  regex constraint) and `schema:valueRequired`. SEEK turns these into **Extended
  Metadata** attributes automatically.

## Using it from the web UI

The **SEEK** adapter is listed on the **Plugins** page (`/settings`) — enabled by
default when its extra (`httpx` + `rdflib`) is installed. While enabled, the
*Export to SEEK* page at `/seek` offers a **Download SEEK ISA RDF (.ttl)** button
that exports the currently loaded dataset; disabling the adapter hides it (404).

## Then, in SEEK

1. As an instance admin, enable the import feature once: *Server administration →
   Enable/disable features → FAIR Data Station import* (and *Observation units*).
2. Open your **Project → Import from FAIR Data Station** and upload the `.ttl`.
   SEEK builds the Investigation/Study/Assay/Sample structure and derives the
   Extended Metadata Types from the RDF.

## Two-phase API integration (provision → sync)

Besides the file export above, the `/seek` page drives SEEK directly over its
JSON:API using the **URL + API key** configured on the Plugins page:

1. **Configure the model** (`POST /seek/provision`) — projects the active profile
   onto the SEEK model surface the API actually permits a project member to
   create: **Controlled Vocabularies** (from a field's closed `enum`, term IRIs
   optionally resolved via OLS) and **Sample Types** (from the profile's
   sample-bearing entities, one attribute per field with the right base type).
   Idempotent: a same-named CV/Sample Type is reused, not duplicated.
2. **Sync the dataset** (`POST /seek/sync`) — walks the loaded dataset and creates
   Investigations, Studies, Assays, and Samples (placed in the provisioned Sample
   Types), threading the ids SEEK returns.

```python
from metaseed.seek import (
    client_from_settings, build_provisioning_plan,
    execute_provisioning_plan, sync_dataset_to_seek,
)
seek = client_from_settings({"url": "http://localhost:3001", "api_key": "<token>"})
plan = build_provisioning_plan(profile)                       # pure projection
provisioned = execute_provisioning_plan(seek, plan, project_id=pid)   # idempotent
sync_dataset_to_seek(seek, client, project_id=pid,
                     sample_type_ids=provisioned.sample_type_ids)
```

**Extended Metadata Types** cannot be created over the API (admin-UI only), so
metaseed instead offers a **model-only TTL** (`GET /seek/model-ttl`,
`to_fair_data_station_model_rdf(profile)`) that a SEEK admin feeds to *Extended
Metadata Types → create from FAIR Data Station TTL* — the "hybrid" half of the
flow for custom Investigation/Study/Assay metadata.

## Why this path (and not the config APIs)

SEEK's Extended Metadata Type and ISA Template APIs are **admin-UI-only**
(`POST /extended_metadata_types` redirects to the admin form; `POST /templates`
drops nested attributes). SEEK's FAIR-Data-Station RDF import is the one native,
scriptable path that creates the ISA structure **and** the Extended Metadata from
a single file. Controlled vocabularies (including ontology-backed ones via
`source_ontology` + `ols_root_term_uris`) remain available over the JSON:API.

## Limitations

SEEK reads the ISA hierarchy **positionally** (Investigation → Study →
ObservationUnit → Sample → Assay), not by `rdf:type`. The `isa` profile has no
ObservationUnit level, so entities below Study currently import one level high
(a Study's Samples arrive as ObservationUnits). Investigation and Study
round-trip cleanly; inserting the ObservationUnit layer for full sample/assay
fidelity is a planned follow-up. See GitHub discussion #26 for the full analysis.
