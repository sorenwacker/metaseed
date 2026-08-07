# SEEK object inventory

What metaseed can create in FAIRDOM-SEEK, by which route, and what is still missing. Written because the SEEK requirements surface one at a time — each becomes visible only once the previous one is satisfied — and a per-object table shows them together.

Verified against **SEEK 1.18.1** with `isa_json_compliance_enabled = true`, unless a row says otherwise.

## Routes

metaseed reaches SEEK three ways. They are not interchangeable.

| Route | What it is | State |
| --- | --- | --- |
| **JSON:API** | `POST`/`GET` with a JSON:API document and an API token | Works |
| **ISA form endpoints** | `/isa_studies`, `/isa_assays`, `/templates` — form-encoded bodies with `Accept: text/html`, same API token, no browser session | Works; their JSON branches are unreachable (see [ISA-JSON compliance](seek-isa-compliance.md)) |
| **File + admin upload** | metaseed emits a file, an administrator feeds it to SEEK | Used where no API exists |

The FAIR Data Station import (`.ttl` → full ISA structure) is a fourth route, and is **blocked upstream**: `FairDataStationImportJob` runs without `User.current_user`, so it fails for any file while reporting `COMPLETED`.

## Objects

| SEEK object | Route | metaseed | Status |
| --- | --- | --- | --- |
| Project | JSON:API (read) | `default_project_id` | Works |
| Investigation | JSON:API | `create_investigation`, incl. `is_isa_json_compliant` | Works |
| Study | ISA form (`/isa_studies`) | `create_isa_study` — creates the Study *and* its Source + Sample Collection types | Works |
| Assay stream | ISA form (`/isa_assays`) | `create_isa_assay(assay_class_id=STREAM)` | Works |
| Assay | ISA form (`/isa_assays`) | `create_isa_assay` with `assay_stream_id` | Works |
| Sample Type | ISA form, as part of a Study or Assay | `isa_types.sample_type_attributes` projects a profile entity per ISA level | Works, but no ISA Template attached — see below |
| Sample Type (standalone) | JSON:API | `create_sample_type`, used by provisioning for the FDS file route | Works |
| Sample | JSON:API | `create_sample`, with `assay_ids` + `study_id` | Works |
| Controlled Vocabulary | JSON:API | `execute_provisioning_plan`, from a field's closed `enum` | Works |
| Data File (remote) | JSON:API | `create_data_file`, one per Study | Works |
| ISA tags | JSON:API (read) | `isa_tag_ids`, resolved by title | Works |
| Assay classes | none | constant `ASSAY_CLASS_IDS` | No endpoint exists; ids read from SEEK's own seed fixture |
| **ISA Template** | ISA form, or JSON file + admin upload | **nothing** | **Missing.** Blocks ISA-JSON export |
| Extended Metadata Type | TTL file + admin upload | `to_fair_data_station_model_rdf` → `GET /seek/model-ttl` | Works (admin step required) |
| Observation Unit | FDS file route only | `fairds` synthesises one per Sample | Blocked with the FDS route |

## The one gap that blocks ISA-JSON export

`ISAExporter` reads `sample.sample_type.isa_template.level` (`isa_exporter.rb:750`) to decide whether an assay material is a `data_file` or an `other_material`. A Sample Type built attribute-by-attribute has no template, so the export raises `NoMethodError` however correct the structure is. `SampleType#is_isa_json_compliant?` also requires `isa_template.present?`.

Two ways to supply one, both verified as reachable:

- **Admin upload** — `POST /templates/populate_template` takes a `template_json_file` and is admin-only, processed by `PopulateTemplatesJob`. metaseed would emit the file, following the pattern of `GET /seek/model-ttl`. **This is the chosen route.**
- **Direct creation** — `POST /templates`, form-encoded, does accept nested `template_attributes_attributes` including `isa_tag_id`, `is_title`, `sample_controlled_vocab_id` and `linked_sample_type_id`. Verified: a template was created with the right level and ISA-tagged attributes. Recorded because the note elsewhere that this is admin-UI-only is **wrong** — that holds only for the JSON:API path.

Four templates are needed, one per ISA level: `study source`, `study sample`, and `assay - material` or `assay - data file` depending on the assay level's terminal attribute.

## Why the requirements surfaced one at a time

Each gate is invisible until the one before it passes, which is worth knowing before estimating similar work:

1. The Investigation must be flagged compliant — otherwise the export refuses outright.
2. The Study must own Sample Types — otherwise the export fails on the Study. The flag alone does nothing.
3. With Samples present, the material chain must exist — Source → Sample → assay material, each naming its predecessor, each with a protocol. An Investigation with **no** Samples exports cleanly, which is the empty case, not the working one.
4. Each Sample Type must carry an ISA Template, for its `level`.

Three of the four only appear once a dataset is actually populated. A structure that passes SEEK's own compliance predicates can still fail to export.
