# Authoring a SEEK-ready profile

FAIRDOM-SEEK stores research in a fixed shape — the ISA hierarchy — and metaseed
can only push an entity into SEEK if that entity maps onto it. A profile that
strays from the shape produces datasets that upload *partially*: the entities
that map go in, the rest are silently left behind. These are the rules for a
profile whose datasets upload **completely**.

Start from the built-in **`seek-ready`** profile (Investigation → Study → Assay
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
descriptive fields of the study.

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

Mark one field `is_identifier` and one `is_label` (they may be the same field).
SEEK derives a resource's title from the label; an entity with neither can be
rejected on upload.

### 6. Protocols are fields; SOPs are out

A `protocol` field is fine — it uploads as an ordinary attribute. **SOPs are a
separate SEEK resource that metaseed does not create**, so do not model a profile
around them expecting them to sync. They are optional enrichment, not part of a
clean upload.

### 7. Data files have no role yet

Entities that represent files (a raw data file, a results file) map to SEEK data
files — which metaseed's sync does **not** create. There is no data-file role
today. Such entities are skipped; keep them out of a profile you need to upload
completely, or accept that they stay in metaseed only.

## Checking a profile

Provision and sync a small dataset and read the result banner. If it says
*"N entities were not uploaded"*, the profile has entities that do not map —
work through the rules above until the sync leaves nothing behind. See
[Publishing to FAIRDOM-SEEK](seek-export.md) for the workflow.
