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

## Compliance is not sufficient for export

A compliant structure is what SEEK's *validation* requires. Its *exporter* requires more, and the difference only appears once the Study holds Samples.

`ISAExporter` walks a material chain: a Source sample, the Sample Collection sample produced from it, and the assay sample produced from that — each naming its predecessor in its input attribute. It also refuses a Sample with no protocol value:

```
Sample {2594: expsample} has no protocol
isa_exporter.rb:726  inputs.map  ->  undefined method `map' for nil
```

An Investigation with compliant Studies and **no** Samples exports cleanly, which is misleading: it is the empty case, not the working one.

Two consequences:

- Every Sample the sync creates records the Assay that produced it as its protocol. The Protocol attribute stays optional on the Sample Type, so a Sample created by other means is not refused.
- The material chain needs a profile with the levels to carry it. `seek-ready-template` 2.0 has a single Sample level, nested under Assay, so an assay sample has no predecessor to point at. **3.0** carries the chain: `Study -> Source -> Sample -> AssayMaterial`, each level naming its parent as its input. An `AssayMaterial` names the Assay that measured it by `reference`, because an Assay measures materials derived from many Samples and containment cannot express that.
- Each level's Sample Type is built from its *own* profile entity. Deriving all three from one entity makes every type demand the others' required attributes, and SEEK rejects each Sample for the fields belonging to a different level.

### The export needs Sample Types built from ISA Templates

Even with the chain complete, the export fails:

```
isa_exporter.rb:750   sample.sample_type.isa_template.level
                      undefined method `level' for nil
```

`process_sequence_output` reads each Sample Type's ISA Template to decide whether the material is a `data_file` or an `other_material`. A Sample Type built attribute-by-attribute — which is the only thing the API allows — has no template, so the export raises regardless of how correct the structure is.

Sample Types can be created from a template (`template_id` is permitted on `POST /sample_types`), but **Templates themselves cannot be created over the API**: `POST /templates` drops the nested attributes, and the ISA Template API is admin-UI-only. So the export path is gated on a template being installed by an administrator first, and on the profile's fields matching it.

This is the deepest of the upstream gates found, and unlike the others it has no workaround from the client side.

## Current status

The sync builds compliant, **exportable** content: Investigations carry `is_isa_json_compliant`, each Study owns a Source and a Sample Collection Sample Type, each Study gets one assay stream, every Assay hangs off it owning its own Sample Type chained to the Study's Sample Collection type, and Samples are created into their Assay's type. Sample Types are therefore created per dataset node rather than per profile entity; provisioning still builds its own for the FAIR-Data-Station file route, which matches samples by attribute PID. With the profile's ISA Templates installed (see below), `GET /investigations/{id}/export_isa` returns the pushed structure as ISA-JSON with its assays, sources and samples — `tests/test_seek/test_live.py::test_a_pushed_dataset_is_exportable_as_isa_json` verifies exactly that against a live instance.

**The export request must be authenticated.** SEEK serves an unauthenticated `export_isa` the anonymous view: `200 OK`, but `ISAExporter` silently drops every assay stream whose samples the anonymous user cannot see, so a private or download-shared push exports with `assays: []` and no error. This masqueraded as an exporter defect for a while; the actual defect was `SeekClient._send` attaching the API token only on some code paths. The token now rides on every request the client sends.

Sample placement follows the material chain by depth (Source at 0, Sample Collection at 1, assay material at 2+), with two rules on top:

- A Sample **nested under an Assay** goes in that Assay's own Sample Type, linked to it — the shape profiles without material levels (e.g. `isa` 1.0) use, and the one SEEK itself models. A declared assay reference still wins over tree position.
- A Sample whose chain **never reaches an Assay link** is created in its Study-owned type but reported in `SyncResult.unlinked`: SEEK derives a Sample's Study and Investigation from its Assay association only, so nothing walking the ISA tree from the Investigation reaches such a record and a re-import drops it.

Two SEEK behaviours the sync works around, verified live:

- List routes can serve a **stale read** right after a create (authorization tables are maintained by background jobs): the just-created Sample Types of a new Study can be momentarily absent from `GET /studies/{id}/sample_types`. The type lookups retry briefly until the expected titles appear.
- Deleting a Study does **not** delete its Sample Types — they stay behind as orphans. `SyncResult.sample_types` records the created ones so a caller cleaning up after itself (the live tests do) can remove them.

Creating a Study needs a placeholder `linked_sample_type_id` (see the `ISAStudy` defect above). The sync creates one Sample Type per project named `<profile> ISA placeholder`, reused by title; it is an artifact of that defect, not part of the ISA structure.

## Reading the structure back

`import_from_seek` understands what the sync writes: assay streams are skipped (they are plumbing, not Assays — reading them back doubled the assay count on every round trip), and an assay sample that names an input is recognised as an assay material. Its input links are followed back to the collection Sample and the Source — which live in Study-owned Sample Types no JSON:API relationship walk reaches — and the chain comes back nested `Source -> Sample -> AssayMaterial`, with the input attribute expressed as that nesting rather than kept as a field value.
