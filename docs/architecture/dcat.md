# DCAT Export

Metaseed can describe a dataset with [DCAT](https://www.w3.org/TR/vocab-dcat-3/)
(Data Catalog Vocabulary), the W3C catalog/discovery layer. DCAT is
complementary to the domain content standards (MIAPPE, ISA, Darwin Core, …): the
profile describes *what is inside* a dataset; DCAT describes *that the dataset
exists and where to get it*.

This page covers the DCAT model and the mapping from a metaseed dataset onto it.
RDF/JSON-LD/Turtle serialization is layered on top separately (see issue #28).
The design discussion is #25.

## Class mapping

| metaseed | DCAT |
|----------|------|
| a profile / a collection of datasets | `dcat:Catalog` |
| a built dataset (`DatasetData`) | `dcat:Dataset` |
| a serialized export (YAML/JSON) | `dcat:Distribution` |
| a served API endpoint | `dcat:DataService` |
| versions of a dataset over time | `dcat:DatasetSeries` (DCAT 3) |

The DCAT classes are represented by a small intermediate model in
`metaseed.dcat.model` (`DcatCatalog`, `DcatDataset`, `DcatDistribution`,
`DcatAgent`, `DcatContactPoint`, `DcatChecksum`). It has no RDF dependency; the
serializer consumes it.

## Two profile shapes

The source of dataset-level metadata depends on the profile's root entity:

- **Container-rooted** (MIAPPE/ISA `Investigation`, ENA `Study`): the root
  entity already carries `title`, `description`, dates, `license`, and contacts,
  so most DCAT-AP Dataset properties are **derived** from root-entity fields.
- **Record-rooted** (Darwin Core `Occurrence`, DiSSCo `DigitalSpecimen`): the
  root entity is a single record, not a dataset, so it provides no dataset-level
  metadata. These rely on explicit `CatalogMetadata` (the same pattern Darwin
  Core Archives use with a separate EML metadata document).

## Sourcing dataset metadata

Two sources are merged, **explicit wins**:

1. **Per-profile field map** (`metaseed.dcat.mapping`): each container-rooted
   profile declares which root-entity field supplies each DCAT property
   (e.g. MIAPPE `submission_date` → `dct:issued`, `license` → `dct:license`,
   `contacts` → `dcat:contactPoint`). Record-rooted profiles have no map.
2. **`CatalogMetadata`** (`metaseed.repositories.dataset_repository`): an
   optional, generic dataset-level block (`title`, `description`, `publisher`,
   `license`, `issued`, `contact_name`/`contact_email`, `landing_page`,
   `keywords`, `themes`). It is persisted with the dataset and is the explicit
   source for record-rooted profiles and the override for any profile.

`metaseed.dcat.resolver.build_dcat_dataset` performs the merge; the field-map
maps are intentionally code-level for now (moving them into `profile.yaml` is a
possible later refinement).

## RDF serialization

`metaseed.dcat.serialize` turns the model into RDF — `to_turtle()` and
`to_jsonld()` — by building an `rdflib.Graph` with the DCAT, Dublin Core Terms,
FOAF, and vCard vocabularies. This is the only DCAT module that depends on
`rdflib`; it is imported lazily (never from `metaseed.dcat.__init__`) and
`rdflib` ships behind the optional extra:

```
pip install 'metaseed[dcat]'
```

so the model and resolver remain usable without it.

## Viewing the card

The dev UI exposes a read-only viewer at `GET /dcat` that renders the DCAT card
(Turtle + JSON-LD) for the dataset currently loaded in the editor. It is a
preview of the export/exposure work (#30); a proper harvestable endpoint
(content negotiation, embedded JSON-LD on a landing page) follows there.

## Out of scope for the core adapter

- `dcat:accessURL` / `dcat:downloadURL` are a **publishing** concern — they
  depend on where a dataset is hosted, so they come from the serving layer
  (e.g. metaseed-hub), not the core exporter. `mediaType`, `format`,
  `byteSize`, and `dcat:Checksum` are computed from the emitted file.
- SHACL/DCAT-AP validation is a separate step (#29).
