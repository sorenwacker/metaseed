# Changelog

## v0.12.0 (2026-06-29)

A bidirectional bridge to scientific data repositories: import public metadata
into a validated profile dataset, and export a dataset back to a repository's
submission format. Each adapter is an optional extra, a pure mapper/writer, and
imports without pulling in the web framework. **First step — smoke-tested
against live records and code-reviewed, but not yet validated at scale or
against the real submission systems (except ENA export, which is XSD-valid).**

### New Features
- **ENA** (`metaseed[ena]`): import a study/sample/experiment/run accession into
  the `ena` profile; export ENA SRA submission XML. Files are referenced, not
  downloaded.
- **BrAPI** (`metaseed[brapi]`): import from any BrAPI v2 server (configurable
  URL + optional bearer token) into the `miappe` profile; export BrAPI v2 JSON.
- **PRIDE** (`metaseed[pride]`): import a ProteomeXchange `PXD` project into the
  `pride` profile; export the px `submission.px`.
- **MetaboLights** (`metaseed[metabolights]`): import an `MTBLS` study into the
  `metabolights` profile; export ISA-Tab + the MAF.
- **`metaseed.isatab.to_isatab`**: a shared ISA-Tab writer reused by the
  `metabolights` and `isa` profiles (and a head start for FAIRDOM-SEEK).

### Bug Fixes
- BrAPI read `observationLevel` and block/replicate from the wrong BrAPI v2
  nesting, silently dropping those fields on every conformant server
- ISA-Tab export duplicated each study's factors/protocols/assays into every
  study and dropped investigation-level contacts for multi-study investigations
- PRIDE `submission.px` lacked the `FMH` header and ordered FME columns wrongly,
  so it would not load as a submission
- MetaboLights dropped a study's contributors and publications (recorded on the
  study, not the investigation)
- ENA file checksums could misalign when a `fastq_ftp` URL segment was empty

### Internal
- The PRIDE and BrAPI clients page through all results (no silent truncation)
- A shared retry helper (`metaseed._http`) retries transient network failures
  (timeouts, connection errors, 429/5xx) across all repository clients
- The ENA export is validated against ENA's official SRA XSD schemas
- Integration approach documented in `docs/architecture/integration-adapters.md`

## v0.11.0 (2026-06-28)

### New Features
- DCAT export: a profile's dataset can be rendered as a DCAT catalog card in
  JSON-LD and Turtle. Mapping is spec-driven via a per-field `dcat:` annotation
  in `profile.yaml` (spec_version 0.5); RDF serialization uses rdflib behind the
  optional `metaseed[dcat]` extra. The UI exposes a card viewer with copy/download
  and an editor for explicit catalog metadata, so record-rooted profiles (Darwin
  Core, DiSSCo) also get a real card (#24, #27, #28, #53, #54, #58)
- Spec-builder MCP: `spec_*` tools to create and edit profiles over MCP, sharing
  the SpecBuilder engine with the UI (#51)
- `metaseed.forms`: framework-agnostic, profile-driven form generation that other
  apps can reuse without importing the web app
- Public `metaseed.list_profiles()` entry point
- `InvalidSpecError` raised by `MetaseedClient.from_spec`/`from_yaml`

### Bug Fixes
- MCP session state no longer reverts to the default profile after
  `create_dataset` (#32); fixed the deeper root where importing the UI installed
  the MCP context at import time — it now installs in the app lifespan
- DCAT serialization produces valid RDF for identifiers/URLs containing spaces or
  other non-IRI characters; the DCAT routes return a clean error instead of a 500
- `convert` honors `--profile` instead of defaulting to `miappe`
- `update_entity` returns the updated entity, not the pre-update snapshot
- A missing required field is reported once, not twice
- `batch_create` auto-fills reference fields like `create_entity`
- Spec merge resolves constraint-only field differences via the chosen strategy
  (e.g. most-restrictive wins) instead of silently taking the first spec
- The entity form fires the correct HTMX event via an explicit flag rather than
  matching the message text

### Internal
- The FastAPI app is loaded lazily from `metaseed.api`, so importing `metaseed`
  (or any submodule) no longer pulls in FastAPI/Starlette or the UI app
- Full multi-agent codebase review recorded in `docs/REVIEW.md`; all gates green
- Run tests in parallel (pytest-xdist); remove dead code

## v0.10.0 (2026-06-23)

### New Features
- Attach relational hints (`expected_children`, `typical_next`,
  `cross_ref_consumers`) to each `batch_create` result, matching
  `create_entity`, so agents building datasets in bulk keep the same guidance
  toward cross-referenced entities (#17)

## v0.9.2 (2026-06-23)

### Bug Fixes
- Make the ENA Sample fields `collection_date` and `geographic_location_country`
  optional. They are checklist-level attributes (e.g. checklist ERC000011), not
  properties of the base Sample, so requiring them universally blocked import of
  valid public ENA/DDBJ samples that omit them (#20)

## v0.9.1 (2026-06-17)

### Bug Fixes
- Materialize inline nested entity items (e.g. a File added under a Run) as
  standalone child nodes on save, so they appear in the tree and exports like
  entities created via the MCP

### Internal
- Update the ruff pre-commit pin to 0.15.7 and migrate the deprecated TCH rule
  codes to TC, so the formatter stops rewriting unrelated files
- Mark the browser-driven selenium tests and exclude them from the pre-push hook

## v0.9.0 (2026-06-16)

### New Features
- Add a "Stop Physics" control to freeze the entity-graph force simulation
- The MCP server advertises a usage workflow on connect (initialize instructions),
  so clients read the profile schema before creating entities

### Bug Fixes
- Persist the node id in saved datasets so the entity graph no longer re-adds
  unchanged nodes on every poll (the permanent "pop-in" / continuous redraw)
- Reject an unsupported entity type with the active profile's supported types and
  a closest-match suggestion instead of a dead-end "Unknown entity type" error

### Internal
- Make the MCP extraction prompts profile-agnostic (drop hardcoded MIAPPE examples)

## v0.8.1 (2026-06-15)

### Bug Fixes
- Respect the explicit TSV delimiter instead of letting the CSV sniffer override it
- Read Excel sheet names before closing the workbook
- Return 404 instead of a 500 when bulk-updating a field that is not nested

### Internal
- Make dataset entity-type detection profile-agnostic (no hardcoded MIAPPE field names)
- Resolve nested entity types from the spec only; remove field-name guessing
- Correct inaccurate docstrings, add missing type annotations, and record the review-appendix triage

## v0.8.0 (2026-06-15)

LLM relationship-guidance tooling for the MCP server (closes #17). All tools derive
from the active profile's schema and work for any spec.

### New Features
- `get_profile_relationships`: per-entity identifier, child types, and cross-references
- `get_example_dataset`: one cross-referenced instance of every entity type
- `validate_relationships`: flag empty references, unreferenced entities, and empty containers
- `validate_ontology_terms`: check `ontology_term` values against OLS with suggestions
- `create_entity` returns relational next-step hints (expected children, cross-reference consumers)
- Template tools and validation errors report the identifier field, field types, format
  constraints, and a note for entities that deviate from the `unique_id` convention

## v0.7.11 (2026-06-15)

### Bug Fixes
- Fix dataset load discarding all entities, causing apparent data loss on reload (#16)
- Stop entities that share an identifier from overwriting each other on load
- Dock the validation panel below the header so its close button is reachable

### New Features
- MCP validation errors name the identifier field and hint when an id alias (e.g. `unique_id`) is sent to the wrong type

### Internal
- Send a descriptive User-Agent to EMBL-EBI OLS and credit OLS in the UI and README
- Rename the "Spec Builder" UI label to "Builder"
- Repair the release workflow's test step

## v0.7.10 (2026-06-15)

Full codebase review with 24 confirmed fixes.

### Bug Fixes
- Preserve the `ontologies` field and fix enum loss during profile merges
- Report malformed dates as validation errors instead of aborting the run
- Keep falsy child-entity values (`0`, `False`, `""`) instead of dropping them
- Count nested entities so per-type counts match the total
- Add the missing `column_ontologies` key for unknown entity types

### Internal
- Bring the file repository to parity with the memory backend
- Return a copy from the ontology search cache to prevent caller mutation
- Remove dead code; correct docstrings, typing, and naming

## v0.7.9 (2026-06-10)

- Maintenance release (release tooling).

## v0.7.8 (2026-06-10)

### Bug Fixes
- Case-insensitive profile comparison in `get_or_create_facade`
- Fix display-name case and clarify button labels
- Allow saving drafts with incomplete ontology terms

## v0.7.7 (2026-06-10)

### Bug Fixes
- Allow underscores in ontology term prefixes during validation

### Internal
- Add a pre-push hook that runs tests (skipping network-dependent ones)

## v0.7.6 (2026-06-10)

### New Features
- Add a search filter to the datasets list
- Add `ValidationCheck` for detailed validation reports

### Bug Fixes
- Fix ontology modal single-select behavior; improve styling; remove inline autocomplete

### Specifications
- Use the `ontology_term` type for accession fields; restore the ISA term-accession rule

### Documentation
- Guides for the ontologies field and constraints UI; add an OLS4 browser link

## v0.7.5 (2026-06-10)

### New Features
- Add the `ontologies` field to `FieldSpec` for OLS lookup filtering

### Internal
- Light logo variants with PNG exports; extract helpers to reduce duplication

## v0.7.4 (2026-06-08)

### Bug Fixes
- `serialize()` returns JSON-serializable data (dates and URLs as strings)

### Internal
- Add safety tests against JSON serialization regressions

## v0.7.3 (2026-06-06)

### Bug Fixes
- Remove the internal `_node_id` from dataset serialization
- Use a distinct `data-testid` for the header validate button

## v0.7.2 (2026-06-04)

### New Features
- Add missing constraints to the PRIDE and MetaboLights specs

### Bug Fixes
- Stable graph node IDs using the entity identifier field

## v0.7.1 (2026-06-03)

### Internal
- Apply CropXR Python standards

## v0.7.0 (2026-06-01)

### Bug Fixes
- Make the ontology modal single-select by default

### Internal
- Refactor `facade.py`, standardize `Self` typing, add exception documentation

## v0.6.2 (2026-06-01)

### Documentation
- Add ontology lookup documentation

## v0.6.1 (2026-06-01)

### New Features
- Move up/down buttons for fields in the spec builder

### Internal
- Add open-source community files

## v0.6.0 (2026-06-01)

### New Features
- Explicit rule types and custom messages in the validation system

## v0.5.1 (2026-05-29)

### Bug Fixes
- Fix reference fields, graph edges, and spec-builder tests
- Use a contextvar instead of patching a removed global in tests

### Internal
- Refactor the API: extract helpers, add public accessors, memory optimization
- Ignore all Selenium tests in the release workflow

## v0.5.0 (2026-05-28)

### New Features
- Add the `MetaseedClient` public API with a clean boundary
- Tree serialization format with auto-detect load; `get_entity_label`
- `load_yaml`/`from_yaml` on `ProfileFacade` and `MetaseedClient`
- `skip_validation` for permissive entity editing

### Internal
- Make `invalidate_cache()` public on `AppState`

## v0.4.0 (2026-05-28)

### Breaking Changes
- Remove global state management in favor of dependency injection
- Remove backward-compatibility globals from dataset_manager.py
- MCPContext now required for MCP tools

### New Features
- Add full dataset validation in UI (Validate button in header)
- Add parent-child relationship validation in MCP entity creation
- Add DatasetManagerFactory for managing dataset managers per AppState

### Bug Fixes
- Fix state synchronization between MCP and UI (root cause of dataset loading bugs)
- Fix graph not updating when MCP creates entities
- Fix Explorer and Spec Builder routing

### MIAPPE Profiles
- Add events field to ObservationUnit in MIAPPE 1.1 and 1.2 (matches original spec: "0+ per study/observation unit")
- MIAPPE-HTP already had this field

### Internal
- Create MCPContext dataclass for explicit dependency injection
- Centralize state management in app.state.mcp_context
- Update MCP tool prompts to emphasize importing only explicit data

## v0.3.9 (2026-05-28)

### Spec Builder Enhancements
- Add copy to clipboard button for YAML preview
- Add edit YAML directly feature with Apply/Cancel
- Redesign YAML preview modal with cleaner styling
- Unify all modals with dark theme and larger size
- Fix button alignment in preview header
- Remove non-functional +Relationship button

### MetaboLights Profile
- Fix validation rules to reference merged Assay entity
- Add multi-technique study support documentation
- Clarify when polymorphism is needed vs enum-based differentiation

### CropXR Profile
- Create unified CropXR v1.0 profile with assay-type discriminator
- Combine phenotyping and sequencing into single profile
- Remove old fragmented profiles (cropxr-phenotyping, cropxr-sequencing)

### Documentation
- Add MetaboLights design discussion
- Update JupyterLab demo with MetaboLights example
- Document entity relationships (nested vs reference)

## v0.3.8 and earlier

See git history for previous changes.
