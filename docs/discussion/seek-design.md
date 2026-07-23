# SEEK adapter design: schema setup and data upload

Date: 260720. Status: draft.

This document describes two things:

1. The **structure** of a SEEK metadata configuration (the schema layer) and the
   requirements for setting it up declaratively.
2. How a **client** later uses that configuration to upload research data.

Both derive from one Metaseed profile: the admin projects the profile into SEEK as
configuration; users author profile-conformant data and submit it against that same
configuration.

## 1. Background: the SEEK object model

SEEK organizes research data with the ISA model:

```
Investigation
  └─ Study
       └─ Assay
```

Assets (samples, data files) hang off studies and assays. Two mechanisms carry
custom metadata, and the configuration layer is built from three object types.

### Object types in the configuration layer

- **Controlled Vocabulary (CV)** — a named term list (e.g. `country`, `ena_platform`).
  Referenced by attributes that must take a value from a fixed set.
- **Extended Metadata Type (EMT)** — a set of typed attributes attached to a resource.
  Two flavours:
  - **Nested** (`supported_type: ExtendedMetadata`) — a reusable block of fields
    (e.g. `location`, `experimental_design`, `growth_facility`) that does not attach to
    anything on its own.
  - **Top-level** (`supported_type: Investigation | Study | Assay | ObservationUnit`) —
    attaches to that resource and may embed nested blocks.
- **ISA-JSON Template** — a per-level sample schema (`study source`, `study sample`,
  `assay - material`, `assay - data file`). Templates define their controlled
  vocabularies inline (`CVList`) and drive the creation of SEEK **sample types**, which
  in turn describe the columns of the samples users fill in.

### How the objects reference each other

```
Top-level EMT (Study)
  ├─ attribute (Controlled Vocabulary) ─────────────► CV
  └─ attribute (Linked Extended Metadata) ──────────► Nested EMT
                                                        └─ attribute (CV) ─► CV

Template (level = study sample)
  ├─ Input attribute (Registered Sample List, isaTag=input) ─► upstream level's samples
  └─ attribute (Controlled Vocabulary, inline CVList) ───────► CV (created on populate)
```

Every reference is stored as a **database foreign key to an instance-assigned id**.
This is the crux of the whole problem: the ids are assigned by the target instance at
creation time and differ between instances. A definition authored on one instance
cannot be replayed on another by id.

### Dependency graph and load order

A referent must exist before the object that references it:

```
1. Controlled Vocabularies
2. Nested Extended Metadata Types        (reference CVs)
3. Top-level Extended Metadata Types     (reference nested EMTs and CVs)
4. Templates, in ISA hierarchy order:
     study source → study sample → assay - material → assay - data file
     (each level's Input links to the level above)
```

Loading out of order fails hard ("Couldn't find ExtendedMetadataType id=N").

## 2. Requirements for setting up the schema

The adapter must turn a declarative source into a correctly-linked configuration on any
instance. Detailed requirements live in the SEEK discussion (#26); the essentials:

- **Reference by name, not id.** The source names `location` and `country`; the adapter
  resolves names to instance ids at apply time. No hardcoded ids in the source.
- **Resolve a dependency DAG.** Topologically sort objects; reject cycles and dangling
  references by name before any API call.
- **Validate semantically.** A CV-typed attribute must resolve to the *intended*
  vocabulary, not merely to some existing id. (A wrong id silently links a field to the
  wrong vocabulary — SEEK does not catch this.)
- **Idempotent upsert.** Match existing objects by natural key (title + supported_type +
  group + version, or content hash) and update in place. No duplicates on re-run; no
  orphans from partial failures.
- **Author-time validation.** Malformed inputs (comments, wrong types, missing ISA tags,
  an isa-tag written into `required`) fail locally, not at upload.
- **Pre-flight the feature flags.** `isa_json_compliance`, `isa`, `samples`,
  `project_single_page` must be enabled together; some need a restart / cache clear.
- **Plan / apply / diff.** Dry-run preview with the resolved id map; apply with a clean
  stop on partial failure; drift detection against a live instance.

The apply step produces an **id map** artifact (symbolic name → instance id). This map
is the bridge to the data-upload phase.

## 3. How the client uses the schema to upload data

Once the configuration exists, a user (via the client) submits data that conforms to it.
The client does **not** hardcode ids either — it reads the live configuration from the
target instance and resolves everything by name, exactly like the setup phase.

### 3.1 Mapping profile data to SEEK objects

For a phenotyping study, the model maps as follows:

| Profile / data concept        | SEEK object                         | Backed by            |
|-------------------------------|-------------------------------------|----------------------|
| Study-level metadata          | Study + top-level EMT               | CropXR phenotyping study EMT |
| Biological material (source)  | Study **source** sample type + samples | source template   |
| Observation unit              | Study **sample collection** sample type + samples | observation unit template |
| Measurement (observed var.)   | Assay                               | observation assay template |
| Output data                   | Assay data-file samples / data files | data file template  |

### 3.2 Submission sequence

```
1. Read live config
   - fetch CVs, EMTs, templates from the instance; build a name → id map.
   - fail fast if a required type/template is missing or its version differs.

2. Create the ISA structure
   - Investigation (or reuse an existing one).
   - Study: created together with two sample types seeded from templates
     (source + sample collection). Attach the top-level Study EMT and fill its
     fields, resolving nested blocks (location, experimental_design, growth_facility)
     and CV values (country) by name.

3. Populate samples
   - Generate rows for each sample type from the authored dataset.
   - Respect CV constraints (values must be valid terms) and required flags.
   - Set the Input linkage between levels: a sample-collection row's Input references
     the source sample(s) it derives from; an assay row's Input references the
     sample-collection sample.
   - Submit via the sample API, or via the single-page spreadsheet export/upload
     round-trip (export the sample-type columns, fill, upload).

4. Create assays and link data
   - Add ISA assay(s) from the assay template; link data files to the assay samples.
```

### 3.3 Client responsibilities

- **Resolve, never assume.** Look up template/EMT/CV ids from the live instance every
  run; the same profile targets different instances with different ids.
- **Produce conformant rows.** Validate values against the profile *and* the live CV
  term lists before upload; surface violations to the user at authoring time.
- **Maintain intra-study references.** Sample ids must be unique within a study and the
  Input links between levels must point at ids defined earlier in the same submission.
- **Be idempotent and resumable.** Re-submitting an unchanged dataset should not
  duplicate samples; a partial submission should be resumable.
- **Stay in sync with config.** Because forms are generated from the live configuration,
  a change the admin makes to the schema is reflected in the submission forms without a
  client release.

### 3.4 Why the two phases share a core

Both phases read the same live configuration and resolve by name; both validate against
the same profile; both talk to SEEK through the same client. The setup phase *writes*
the configuration objects; the submission phase *reads* them and *writes* content. This
is why the adapter is one shared engine (`SeekConfigModel`, resolver, `SeekClient`,
`apply`) with two page-sets on top — an admin configurator and a researcher submission
flow — rather than two separate tools.

## 4. Open questions

- REST API coverage vs admin-only endpoints for each object type (affects how much of
  the client is clean API vs form interaction).
- Sample submission: sample API vs single-page spreadsheet round-trip as the primary
  path — which is more robust for bulk data?
- Natural key for matching configuration objects across instances.
- Resumability and idempotency guarantees for large sample submissions.
