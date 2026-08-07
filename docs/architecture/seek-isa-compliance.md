# ISA-JSON compliance

SEEK can hold an ISA structure in two different shapes. The shape metaseed currently writes is accepted, stored and readable, but it is **not ISA-JSON compliant**, and SEEK refuses to export it as ISA-JSON. This page records what compliance requires, how it is reachable over HTTP, and what it costs metaseed to produce.

Verified against **SEEK 1.18.1** with `isa_json_compliance_enabled = true`.

## Prerequisites on the SEEK instance

The feature flags are the ones listed under *Required SEEK settings* in [SEEK Export](seek-export.md) — enabled in that order, under *Server administration → Enable/disable features*. What matters specifically here:

| Prerequisite | Verified value | Why |
| --- | --- | --- |
| `isa_enabled` | `true` | provides Investigation/Study/Assay |
| `samples_enabled` | `true` | provides Sample Types and Samples |
| `project_single_page_enabled` | `true` | prerequisite of ISA-JSON compliance, and the page both ISA endpoints redirect to |
| `isa_json_compliance_enabled` | `true` | puts the instance in ISA mode |
| Seeded ISA tags | 11 | tags are resolved by title; a bare instance has them |
| Seeded assay classes | `EXP`, `MODEL`, `STREAM` | `STREAM` is required to create an assay stream |

One qualification, because it is easy to over-read: `isa_json_compliance_enabled` is **not** consulted by `ISAStudiesController`, `ISAAssaysController`, `Study#is_isa_json_compliant?`, `Assay#is_isa_json_compliant?`, or `ISAExporter::Exporter`. Only the views check it. Turning it off therefore does not stop the sequence below from working or the export from succeeding — it hides SEEK's ISA affordances in the UI. Compliance is enforced by structure, and the flag is what makes that structure visible to a user.

Beyond the flags, the API token must belong to a person who is a **member of the target project**: every resource is created with that person as contributor, and the ISA endpoints read `User.current_user` directly.

## What compliance is

`is_isa_json_compliant` is a boolean column on Investigation, and a derived predicate on Study and Assay:

| Level | Predicate | Requirement |
| --- | --- | --- |
| Investigation | `is_isa_json_compliant` | the column is set |
| Study | `Study#is_isa_json_compliant?` | the Investigation is compliant **and** the Study owns at least one Sample Type |
| Assay | `Assay#is_isa_json_compliant?` | the Investigation is compliant **and** the Assay owns a Sample Type, or is an assay stream |

Compliance is therefore structural, not a label. Setting the flag alone does not make a Study compliant, and does not make the Investigation exportable.

## Why it matters

`ISAExporter::Exporter` refuses a non-compliant Investigation outright:

```
Only ISA-JSON compliant investigations can be exported to an ISA-JSON
```

Every Investigation metaseed creates today has `is_isa_json_compliant = nil`, so none of them can be exported as ISA-JSON. Setting the flag on an existing metaseed Investigation does not fix it: the export then fails on the Study, which owns no Sample Types.

## What compliance requires

A Study owns exactly two Sample Types, in order, and the second links to the first:

1. **Source** — its attributes carry the `source` and `source_characteristic` ISA tags.
2. **Sample Collection** — carries `protocol`, `sample` and `sample_characteristic` tags, plus an *input attribute*: type `Registered Sample List`, ISA tag `input`, `linked_sample_type_id` pointing at the Source type.

An Assay hangs off an **assay stream** (an Assay whose class is `STREAM`) via `assay_stream_id`, and owns its own Sample Type, which must have:

- exactly one attribute tagged `protocol`,
- exactly one tagged `data_file` **or** `other_material`,
- an ISA tag on *every* attribute,
- an input attribute linking back to the previous Sample Type in the chain.

The chain is what makes the stream a stream: `Assay#first_assay_in_stream` matches on `sample_type.previous_linked_sample_type == study.sample_types.second`. Streams are held together by linked Sample Types, not by tree position.

ISA tags are looked up by title rather than id — the numeric ids are seeded per instance and are not part of any published contract.

## The transport: two APIs, not one

The ISA structure is not reachable over the JSON:API alone.

| Resource | Endpoint | Encoding |
| --- | --- | --- |
| Investigation (incl. the compliance flag) | `POST /investigations` | JSON:API |
| Study + Source + Sample Collection types | `POST /isa_studies` | form-encoded |
| Assay stream | `POST /isa_assays` | form-encoded |
| Assay + its Sample Type | `POST /isa_assays` | form-encoded |
| Sample | `POST /samples` | JSON:API |

`/isa_studies` and `/isa_assays` back SEEK's web forms, but they authenticate with the same API token and need no browser session. Two things force their use:

- `assay_stream_id` is absent from `assay_params` and from the `assayPost` schema, so `POST /assays` accepts it, answers `200 OK`, and discards it.
- `SampleType has_and_belongs_to_many :studies`, but `study_ids` is not permitted on `POST /sample_types`, so a Sample Type cannot be attached to a Study over the JSON:API.

Both endpoints require form encoding. Their `format.json` branch is unreachable: `check_json_id_type` demands a JSON:API `data` member, and `convert_json_params` then drops the `isa_assay` / `isa_study` key. Repeated form keys must use `[]` rather than numeric indices — indexed keys parse as a Hash, which the controller iterates as an Array and crashes with a `TypeError`.

## The verified request sequence

Each step returns `302`; the whole sequence needs only an API token.

1. `POST /investigations` with `is_isa_json_compliant: true`.
2. `POST /isa_studies` with the Study, the Source type and the Sample Collection type. The Sample Collection's input attribute needs a `linked_sample_type_id` that passes validation before `ISAStudy#save` overwrites it with the real Source type — validation runs before the link is assigned, so any existing Sample Type id serves as a placeholder.
3. `POST /isa_assays` with `assay_class_id` = the `STREAM` class to create the stream.
4. `POST /isa_assays` per assay, with `assay_stream_id`, `input_sample_type_id` (the Study's Sample Collection type) and the assay's own tagged Sample Type.
5. `POST /samples` as today.

The result exports: `ISAExporter::Exporter` returns an ISA-JSON document with the study, its assays, and `materials` containing `sources` and `samples`.

## What this costs metaseed

**Provisioning becomes dataset-shaped.** Sample Types are currently derived from the profile — one per sample-bearing entity, shared across every Assay that uses it. A compliant stream needs one Sample Type *per assay instance*, because each type links to the previous one in that assay's chain. Two assays of the same profile entity need two Sample Types with different links, which a profile-time projection cannot express.

**Profiles need ISA tags.** Every attribute of a compliant Sample Type carries an ISA tag, and the tag set is constrained per level. `FieldSpec` has no field for this today, so the profile cannot say which of its fields is the protocol, which is the data file, and which are characteristics.

**Ordering becomes significant.** `study.sample_types.first` and `.second` are load-bearing — Source and Sample Collection respectively. Nothing in the current model records that ordering.

## Upstream defects encountered

Reported separately; none has a workaround inside SEEK's settings.

| Defect | Effect |
| --- | --- |
| `POST /assays` silently discards `assay_stream_id` | `200 OK` for a structure that was not built |
| `/isa_assays` and `/isa_studies` have unreachable `format.json` branches | JSON callers get `422` or `500` regardless of body |
| Hash-shaped `sample_attributes` raise `TypeError` | `500` instead of a `4xx` |
| `isa_exporter.rb:42` interpolates bare `investigation` instead of `@investigation` | the "studies should be ISA-JSON compliant" error raises `NameError`, masking the real cause |
| `ISAStudy` validates the input attribute's link before `save` assigns it | a placeholder `linked_sample_type_id` is required to create a Study |

## Current status

Not implemented. metaseed writes non-compliant Investigations, Studies without Sample Types, and flat `EXP` Assays sharing one profile-derived Sample Type per entity. That structure round-trips through metaseed's own importer and is covered by tests; it cannot be exported as ISA-JSON, and its Assays do not render in SEEK's ISA study view.
