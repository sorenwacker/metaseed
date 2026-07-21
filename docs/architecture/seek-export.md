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
