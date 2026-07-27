# DCAT Export

Metaseed can describe a dataset with [DCAT](https://www.w3.org/TR/vocab-dcat-3/)
(Data Catalog Vocabulary), the W3C catalog/discovery layer. DCAT is
complementary to the domain content standards (MIAPPE, ISA, Darwin Core, …): the
profile describes *what is inside* a dataset; DCAT describes *that the dataset
exists and where to get it*.

This page covers the DCAT model, the mapping from a metaseed dataset onto it, and
the RDF serialization. The design discussion is #25.

Metaseed targets **DCAT 3**, the current W3C Recommendation. DCAT 2 and 3 share
the `http://www.w3.org/ns/dcat#` namespace, so this is a matter of which terms
are used rather than which IRI. One practical consequence: rdflib ships `DCAT` as
a closed list of DCAT 2 terms, so DCAT 3 additions such as `dcat:version` are
emitted through `metaseed.dcat.serialize.DCAT3`, an unvalidated view of the same
namespace. The RDF is identical either way; without it a valid term looks like a
typo in rdflib's warnings.

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

1. **Per-field `dcat` annotations in the spec** (spec_version 0.5+): each
   container-rooted profile's root entity annotates its fields with the DCAT
   property they fill (e.g. MIAPPE `submission_date: {dcat: dct:issued}`,
   `license: {dcat: dct:license}`, `contacts: {dcat: dcat:contactPoint}`). The
   mapping is declared in `profile.yaml`, not in code — so any profile,
   including ones built in the Spec Builder, can self-describe its DCAT mapping.
   See [DCAT Mapping](../api/schema-specs.md#dcat-mapping). Record-rooted
   profiles have no such annotations.
2. **`CatalogMetadata`** (`metaseed.repositories.dataset_repository`): an
   optional, generic dataset-level block (`title`, `description`, `publisher`,
   `license`, `issued`, `contact_name`/`contact_email`, `landing_page`,
   `keywords`, `themes`). It is persisted with the dataset and is the explicit
   source for record-rooted profiles and the override for any profile.

`metaseed.dcat.resolver.build_dcat_dataset` reads the root entity's field specs
(their `dcat` annotations) and merges in the explicit `CatalogMetadata`.

### Which way the derivation runs

A repository accession carried by a dataset — an ENA `PRJEB…`, a PRIDE `PXD…`, a
MetaboLights `MTBLS…` — is annotated `dct:source`, not `dct:identifier`. That is
the *default*, not a universal truth, and the distinction matters.

The direction is genuinely ambiguous from the field alone. A dataset **imported**
from ENA is derived from ENA's record, and claiming ENA's accession as its own
identifier would make two records assert one identity — a harvester reads the
card as a duplicate, and any FAIR score it shows is borrowed from ENA's
persistent identifier. But a dataset **authored here for submission**, whose
accession ENA later assigned to *it*, is the origin: there the accession really
is this dataset's identifier, and `dct:source` understates it.

Nothing in a dataset records which happened. `create_dataset_from_accession`
discards the accession it imported by, and the value survives only as an
ordinary, user-editable field. So the spec makes the claim that is safe in both
directions — "this record relates to that accession" — and a platform that
*knows* it originated the dataset promotes it, by passing the accession as the
identifier when it builds the card (`fallback_identifier`, or the publication
context once a caller supplies one). Understating provenance is recoverable;
falsely claiming someone else's identifier is not.

`dct:source` is serialized alongside `prov:wasDerivedFrom`, which states the same
fact for a provenance reader. One model field drives both so they cannot drift.
`dct:isVersionOf` is reserved for the narrower case of a straight copy.

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

## Downloading the record

The card is a registered export action, so every host that reads the adapter
registry offers it:

```python
from metaseed.dcat.export import to_dcat

files = to_dcat(client)   # {"dcat.jsonld": ..., "dcat.ttl": ...}
```

It is declared with `profiles=("*",)` — offered for **every** profile, not just
one. That wildcard exists for this case: a catalogue record describes a dataset
whatever standard its content follows, and the `dcat` adapter key names a
vocabulary rather than a profile, so the registry's usual "an adapter's key names
the profile it serves" convention would have offered it to nothing. It also
reaches profiles authored in the Spec Builder, whose names cannot be enumerated
here.

`to_dcat` emits the **dataset**, not a `dcat:Catalog` wrapping it: a catalogue
serializes to a JSON-LD `@graph`, which is the wrong shape for a consumer asking
about one dataset and cannot be embedded in a page as-is. An empty dataset
returns an empty mapping, which hosts already report as nothing to export, rather
than a valid-looking record describing nothing.

`metaseed.dcat.export.build_card` is the shared resolution step, used by both the
export and metaseed's own `/dcat` page, so the page and the downloaded file
cannot describe the same dataset differently.

## Publishing the record elsewhere

metaseed resolves what a dataset *is*. Where it can be fetched, what identifies
it, and what may be done with it belong to whatever platform publishes it — a
repository deposit, a portal, a lab's own site. `metaseed.dcat.publication` is
how that platform supplies them:

```python
from metaseed.dcat import PublicationContext, build_published_dataset, origin_url

published = build_published_dataset(
    card,
    PublicationContext(
        landing_page="https://data.example.org/d/abc123",
        identifier="https://doi.org/10.5281/zenodo.1234567",   # optional
        license="CC-BY-4.0",
        source=[origin_url("pride", "PXD000001") or ""],
    ),
)
```

`landing_page` is the only required field: without somewhere to fetch the
dataset nothing else is assessable, and it stands in as the identifier until a
DOI exists. The publisher's identifier replaces any derived from content, the
publisher's licence and distributions win, and `source` and `conforms_to` are
merged rather than replaced. The input card is never mutated, so one resolved
card can be published to a staging URL and a real one without the first leaking
into the second.

`spdx_license_uri` upgrades a bare `"CC-BY-4.0"` to its spdx.org URI and passes
an explicit URL through — a licence a consumer cannot resolve is not
machine-readable. `origin_url` builds the landing page for a record in ENA,
PRIDE, or MetaboLights, and returns `None` for a profile with no repository
rather than guessing a URL that will not resolve.

This module is pure, so a host can build a published card without the
`metaseed[dcat]` extra and serialize it wherever it likes.

## Viewing and editing the card

The UI's **DCAT** panel shows the card (Turtle + JSON-LD) for the loaded dataset,
with copy/download buttons and an editor for the explicit `CatalogMetadata`
(title, description, publisher, license, keywords). The editor posts to
`POST /api/dcat/metadata`; the values are held on the session state and
round-tripped through dataset save/load. This is how record-rooted profiles
(Darwin Core, DiSSCo) supply the dataset-level metadata they cannot derive.
A standalone read-only page is also served at `GET /dcat`.

A proper *harvestable* endpoint (content negotiation, embedded JSON-LD on a
landing page) is the remaining export step (#30).

## Out of scope for the core adapter

- `dcat:accessURL` / `dcat:downloadURL` are a **publishing** concern — they
  depend on where a dataset is hosted, so they come from the serving layer
  (e.g. metaseed-hub), not the core exporter. `mediaType`, `format`,
  `byteSize`, and `dcat:Checksum` are computed from the emitted file.
- SHACL/DCAT-AP validation is a separate step (#29).
