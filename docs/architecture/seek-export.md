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

## Workflow: configure once, populate per dataset

The flow has two roles, mirroring how SEEK itself is used — an **admin** sets a
project up once, then **users** populate it repeatedly:

| Role | Step | Frequency |
|------|------|-----------|
| Admin | Create the SEEK **project**; enable the feature flags below | once per instance/project |
| Admin | **Provision** the profile's model into that project — Controlled Vocabularies + Sample Types (`execute_provisioning_plan`) | once, then only when the profile changes |
| User | Author a dataset in metaseed, download its RDF, and **import** it into the project | per experiment |

Each import adds **one Investigation** (Investigation → Study → ObservationUnit →
Sample) to the shared project — it does **not** create a new project. A new
project is only made when an admin explicitly creates one. The provisioned Sample
Types are reused across every user import; re-provisioning is idempotent (a
same-named CV/Sample Type is reused as-is — editing a provisioned type's columns
is left to an admin, see [Updating existing content](#updating-existing-content)).

## Using it from the web UI

The **SEEK** adapter is listed on the **Plugins** page (`/settings`) — enabled by
default when its extra (`httpx` + `rdflib`) is installed. While enabled, the
*Export to SEEK* page at `/seek` offers, per the two roles above: **Provision
model** (pick profile + project) to configure the SEEK model, and **Download SEEK
ISA RDF (.ttl)** to export the currently loaded dataset for import. Disabling the
adapter hides the page (404).

The project a **provision** or JSON:API **sync** targets is chosen from the
project dropdown on the `/seek` page. The downloaded **RDF is project-agnostic** —
for the file-import path the project is decided in SEEK, by which project's
*Import from FAIR Data Station* page you upload it to.

## Required SEEK settings

The *Import from FAIR Data Station* action only appears once a chain of feature
flags is enabled. All live under *Server administration → Enable/disable features*
(`/admin/features_enabled`), and each states its own prerequisites in SEEK's UI.
Enable them in this order:

| Setting (SEEK label) | Section | Requires | Why it is needed |
|----------------------|---------|----------|------------------|
| Single page enabled | SEEK features | — | Prerequisite of ISA-JSON compliance |
| ISA enabled | Resource Types | — | Provides Investigation/Study/Assay |
| Samples enabled | Resource Types | — | Provides Sample Types and Samples |
| Compliance with ISA-JSON schemas enabled | SEEK features | Single page, ISA, Samples (SOPs recommended) | Instance-wide ISA-JSON schemas the import targets |
| Observation Units enabled | Resource Types (under ISA) | ISA | FDS builds Investigation → Study → **ObservationUnit** → Sample |
| FAIR Data Station enabled | Resource Types (under ISA) | ISA **and** Observation Units | Exposes the import/update action itself |

Feature flags are cached: after toggling, a change may need an application restart
or cache clear before the action appears. Verify the two ISA sub-options
(*Observation Units*, *FAIR Data Station*) show as enabled before importing.

## Then, in SEEK

1. With the settings above enabled, open your **Project → Import from FAIR Data
   Station** and upload the `.ttl`. SEEK builds the
   Investigation/Study/ObservationUnit/Sample structure and derives the Extended
   Metadata Types from the RDF.

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

## Sample import: how the pieces line up

Investigation and Study round-trip from the RDF with no extra setup. **Samples**
need the provisioned Sample Type and the RDF to agree on five points that SEEK's
FDS reader (`lib/seek/fair_data_station/`, verified against SEEK 1.18.1) imposes.
`execute_provisioning_plan` and `to_fair_data_station_rdf` now satisfy all five —
they are recorded here because each is a silent hard requirement, and the
domain ontology plays **no** part in the matching.

1. **A Sample Type must pre-exist; matching is by attribute PID string.** The
   import never creates Sample Types — it matches each RDF sample to an existing
   one by exact-string equality of attribute `pid` URIs, needing at least one
   shared non-blank PID (`sample.rb#find_closest_matching_sample_type`). The data
   RDF emits each field as `http://schema.org/<field>`, so *that* URI is the PID —
   not the field's ontology term (e.g. `PPEO:hasPlantAnatomicalEntity`).
   → provision sets each attribute's `pid` to the same `http://schema.org/<field>`
   URI the RDF emits, so the two paths meet.

2. **Blank PIDs never match.** SEEK drops blank PIDs (`compact_blank`); an
   attribute a sample should populate must carry the URI from (1). → provision
   assigns PIDs to every field attribute (a `MissingSampleTypeException` means this
   is absent).

3. **The Sample Type must be viewable by the importer.** The matcher only
   considers types `authorized_for(:view, person)`. Because the same person
   provisions and imports, the type's contributor already has view access, so it
   is created private (SEEK's default). Sharing it more widely is subject to the
   instance's sharing limits, which reject an over-permissive policy over the API.

4. **`Title` and `Description` attributes, exact case.**
   `sample.rb#populate_seek_sample` assigns `data['Title']`/`data['Description']`,
   which must map to attributes titled exactly `Title` and `Description`;
   attribute-name uniqueness is case-insensitive, so a lowercase `description`
   would collide. → provision leads every Sample Type with a `Title` (the
   `is_title` attribute) and `Description`, and does not emit core identity/
   description fields as separate attributes.

5. **Every sample needs a title, from `schema:title`.** MIAPPE samples have no
   title field — they are keyed by `unique_id`, emitted as `schema:identifier` —
   so without more the required `Title` is blank and the sample is invalid. →
   `to_fair_data_station_rdf` emits `schema:title` (and `schema:name`) for every
   instance, falling back to the identity when the entity has no title field.

## Updating existing content

Re-importing through *Import from FAIR Data Station* is **create-only**: it errors
if an Investigation with the same external identifier already exists. To change an
imported Investigation, use its own **Actions → Update from FAIR Data Station**
(`update_from_fairdata_station`), which runs SEEK's `update_isa` and reassigns
attributes in place — updating field values (including descriptions) and adding
new samples, matched by external identifier, without duplicating.

SEEK's external identifier **is** `schema:identifier`, which the RDF emits from
each entity's `unique_id`. So an update keys on `unique_id`: keep it stable across
edits — **changing `unique_id` makes SEEK create a new resource instead of
updating the existing one.**

**Adding a column** (a new profile field on a sample-bearing entity) is a schema
change on the Sample Type. `execute_provisioning_plan` does **not** edit an
existing Sample Type — it reuses it as-is. Editing attributes over the JSON:API
means PATCHing the whole `sample_attributes` list, which would drop attribute
facets SEEK holds but the API does not read back (`allow_cv_free_text`,
`description`, `unit`, sample-type links) and can duplicate `is_title`/`pos`. So a
new column is added by a SEEK admin (or by recreating the type on a clean
project), not automatically.

## Manual UI test

End-to-end, driving both apps by hand:

1. **metaseed** (`/`) — build or load a dataset in the target profile (e.g. MIAPPE).
2. **metaseed** (`/seek`, *Configure the model*) — pick the profile + project and
   **Provision model** to create the Sample Type in SEEK.
3. **metaseed** (`/seek`, *Or export a file*) — **Download SEEK ISA RDF (.ttl)**.
4. **SEEK** — target Project → Actions → **Import from FAIR Data Station** → upload
   the `.ttl`, set sharing, Submit. The Investigation/Study/ObservationUnit/Samples
   appear in the project.
5. **Update** — edit values in metaseed, re-download the RDF, then in SEEK on the
   imported Investigation → Actions → **Update from FAIR Data Station** → upload.

## Importing from SEEK (SEEK → metaseed)

The read direction mirrors the export: `import_from_seek(seek_client,
investigation_id)` walks a SEEK Investigation over the JSON:API
(Investigation → Study → ObservationUnit → Sample), reads each Sample's
`attribute_map` plus the ISA core fields, and reconstructs a metaseed dataset.

```python
from metaseed.seek import client_from_settings, import_from_seek

seek = client_from_settings({"url": "https://fairdomhub.org"})  # public read needs no key
dataset = import_from_seek(seek, "8")     # -> a MetaseedClient
```

Because SEEK's Sample Types and Extended Metadata are user-defined, the profile is
**derived from the instance** (one entity per ISA level; Sample fields taken from
the Sample Types encountered) rather than assumed — so no field is dropped. The
derived-spec dataset re-exports through `to_fair_data_station_rdf` (which reads the
facade's in-memory spec), closing the loop: pull from one instance
(e.g. FAIRDOMHub), edit, push to another (e.g. a local instance).

Instances without ISA-JSON compliance answer the `observation_units` sub-route
with a 4xx; the import degrades gracefully to the Investigation/Study skeleton
(no samples) rather than aborting. Full Extended-Metadata fidelity
(reconstructing custom EMT attribute types) is a follow-up; core ISA + Sample
fields round-trip today.

## Status of the JSON:API sync path

The `POST /seek/sync` / `sync_dataset_to_seek` path (creating Investigations/
Studies/Assays/Samples directly over the JSON:API) predates the FAIR-Data-Station
route and is **not idempotent** — re-running it duplicates the ISA tree rather
than updating in place. Prefer the RDF import/update path above, which SEEK
matches by external identifier. The JSON:API sync remains for the flat
push-samples case and is a candidate for deprecation.

## Positional hierarchy note

SEEK reads the ISA hierarchy **positionally** (Investigation → Study →
ObservationUnit → Sample → Assay), not by `rdf:type`. A profile therefore needs an
ObservationUnit level between Study and Sample for samples to land at the right
depth; the `miappe` profile has one, the `isa` profile does not (its Study-level
Samples import one level high, as ObservationUnits).
