# Authoring a SEEK-ready profile

FAIRDOM-SEEK stores research in a fixed shape — the ISA hierarchy — and metaseed
can only push an entity into SEEK if that entity maps onto it. A profile that
strays from the shape produces datasets that upload *partially*: the entities
that map go in, the rest are silently left behind. These are the rules for a
profile whose datasets upload **completely**.

Start from the built-in **`seek-ready-template`** profile (Investigation → Study → Assay
→ Sample). Clone it, add your own fields, and keep the shape. A dataset built on
it syncs to SEEK with nothing skipped — verified in the test suite against a live
instance.

## The shape SEEK accepts

SEEK has exactly these containers, and nothing else:

| SEEK / ISA role | What it is |
|-----------------|------------|
| Investigation | the overarching project (the root) |
| Study | a study within it |
| ObservationUnit | an optional level between Study and Sample |
| Sample | a material or biological sample |
| Assay | a measurement performed on samples |
| (Data file) | a file attached to an assay — **not yet synced by metaseed** |

Every entity in your profile must map to one of these, through its **SEEK role**
(set on the entity in the Spec Builder). An entity with no role, and whose name
is not one of these, is skipped on sync — its data never reaches SEEK.

**Leave ObservationUnit out unless you need it.** It is the level most likely to
misplace data: without it, Samples and Assays hang directly off the Study, which
is the simplest correct mapping. Add an ObservationUnit level only when your data
genuinely has one (repeated measures on the same subject, for instance).

## The rules

### 1. Every entity gets a role

Give each entity a SEEK role. If an entity does not describe an Investigation,
Study, Assay or Sample, it does not belong in the hierarchy — see the next rule.

### 2. Fold one-per-study context into the Study

A profile often has context tables — a Location, a GrowthFacility, an
ExperimentalDesign — that describe *the study* and occur once per study. These
have no SEEK role, because SEEK has no "reference table" concept. Do not leave
them as separate entities; they will be skipped.

Instead, **move their fields onto the Study** (prefix to avoid clashes:
`site_country`, `facility_description`, `design_type`). On upload they become the
Study's **Extended Metadata** in SEEK — which is exactly what they are: extra
descriptive fields of the study. This needs the Study to name an Extended Metadata Type installed on the SEEK (`seek.extended_metadata`); without one, the fields reach SEEK only in the ISA-JSON export and are marked as such (rule 8).

### 3. No normalized reference tables

SEEK's model is denormalized. A lookup table shared across many rows (a list of
instruments, a set of protocols) has no home. Either fold it in (rule 2), or
express it as a **closed `enum`** on the field that uses it — an enum becomes a
Controlled Vocabulary in SEEK, which *is* a shared lookup.

### 4. A list field must be an enum, or expect it flattened

A field of type `list` with a closed `enum` becomes a Controlled Vocabulary List
in SEEK and keeps its multiple values. A `list` field **without** an enum
becomes a single Text attribute, so its values are joined into one string on
upload. If you need multiple distinct values preserved, give the field an enum.

### 5. Give every entity an identifier and a label

Mark one field `is_identifier` and one `is_label` (they may be the same field). SEEK derives a resource's title from the label; an entity with neither can be rejected on upload. An Investigation, Study or Assay record has no identifier attribute in SEEK (the `investigationPost`, `studyPost` and `assayPost` schemas of its API), so on those entities the `title` is both: mark it `is_identifier` and `is_label`, and add no separate identifier field. An Assay also needs SEEK's required `assay_class` (`EXP` experimental, `MODEL` modelling) and `assay_type` (a JERM ontology URI); the sync sends the record's values, and an Assay without them is created as an experimental assay of the default type.

### 6. SOPs are registered by link

A `protocol` field uploads as an ordinary attribute. A protocol document of its own is an SOP: give the entity the `SOP` role and nest it under the Assay that follows it (or under the Study when no single Assay does). The sync registers each SOP in SEEK by its location, a remote content blob like a data file, titled after the record's label and linked to the Assay above it. The location is the entity's `uri` field (or one named `url`, `location` or `file_location`); an SOP without one is reported as skipped. SEEK fetches the location when it registers the SOP, so it must resolve from the SEEK server; one that does not is reported with the location named. A second push finds an SOP already registered under the same title in the project and reuses it.

### 7. Data files are registered by link

An entity with the `DataFile` role is registered in SEEK as a data file pointing at its location; the file itself stays where it is. See [Publishing to FAIRDOM-SEEK](seek-export.md).

### 8. Mark the fields SEEK has no attribute for

An Investigation, Study or Assay record in SEEK has a fixed set of attributes (title, description; an Assay also `assay_class`, `assay_type` and `technology_type`), plus the attributes of an Extended Metadata Type when the entity names one in `seek.extended_metadata`. Any other field on such an entity reaches SEEK only inside the ISA-JSON export, not as a record attribute. Mark it with `seek_isa_only: true` and say so in its description:

```yaml
- name: submission_date
  type: date
  description: When the metadata was submitted. Carried in the ISA-JSON export only; SEEK's Investigation has no such attribute.
  seek_isa_only: true
```

A marked field is left out of the record's Extended Metadata, the SEEK preview lists it as ISA-JSON only, and the shipped profiles are gated: a test fails when the latest version of a profile has an unmarked field on an Investigation, Study or Assay entity that SEEK cannot hold.

## Checking a profile

Provision and sync a small dataset and read the result banner. If it says
*"N entities were not uploaded"*, the profile has entities that do not map —
work through the rules above until the sync leaves nothing behind. See
[Publishing to FAIRDOM-SEEK](seek-export.md) for the workflow.
