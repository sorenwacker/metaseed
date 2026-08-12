# Changelog

## Unreleased

### Added
- A value in an ontology-term field is checked against the ontologies its field
  names, not merely against OLS at large: a field declaring
  `ontologies: ["to"]` no longer accepts a phenotype term (#215). The pointer
  had been decoration since it shipped.

  Three outcomes rather than two, because a boolean cannot carry the one that
  matters: a value is right, wrong, or **not checked** — and an OLS outage
  produces the third. Someone else's downtime must not mark a researcher's data
  invalid, and a check that silently reports "fine" when it learned nothing is
  worse than none.

- Vocabularies can be held locally, as JSON files kept apart from the
  specifications that use them (`METASEED_VOCABULARIES`). A spec names an
  ontology and says nothing about where its terms come from, so one vocabulary
  serves many specs and is versioned on its own. Several files may declare the
  same ontology and layer in filename order, which is how a project extends a
  vocabulary someone else maintains without forking it; each term remembers
  which file supplied it.

### Fixed
- The ontology-term check runs where a researcher can see it. It existed, and
  was reachable from the library API, the MCP tools and the CV validators, but
  not from `DatasetValidator` — which is what the application validates
  through — so nobody editing a dataset was ever told that a value came from
  the wrong ontology (#215). Reported as rule `ontology_term`; a value that
  could not be checked is still not reported.

  Measured against every shipped example: only miappe/1.1 changes, where it
  surfaces 11 pre-existing contradictions between the profile and the example —
  `scale_accession_number` declares `uo` while the example carries CO_321 scale
  terms, and `event_accession_number` declares `co_715` while the example
  carries AGRO terms. Both are real inconsistencies in shipped content, not
  false positives, and neither the profile nor the example has been changed to
  hide them.
- A dataset written as a nested document loads through the client API. Every
  shipped example returned **0** entities from `load_yaml` — silently — because
  the loader read only the store's own serialization, where each entity carries
  a `_type`, and a document written by a person carries none. The examples are
  the natural source of realistic data for anyone building on metaseed, and
  none of them could be loaded by a consumer (#246). `ProfileFacade.load_nested`
  loads a document directly, honouring `owns` containment and treating a plain
  string in a child field as the reference it is.
- A load that drops every entity now says so. Returning zero quietly is how a
  whole dataset went missing unnoticed; the warning names the method that does
  work.
- A range of quantities is checked as quantities, however the rule is written.
  Routing by operand type first reached only the path that *infers* a rule's
  type; the same parsing existed a second time for rules declaring
  `type: date_range`, so writing that one line of YAML over two numeric fields
  still produced "not a valid date". Both paths now share one parser and one
  builder. Where a declared type contradicts its operands the data wins — a
  numeric field cannot hold a date — and the contradiction is logged rather
  than quietly reinterpreted. No shipped profile declares the type explicitly,
  so no shipped rule changes. Any `A >= B` condition became
  a date-range rule whatever it compared, so Darwin Core's
  `maximumDepthInMeters >= minimumDepthInMeters` reported two floats as "not a
  valid date" and those two fields could never both be populated (#246).
  Comparisons are now routed by the declared type of their operands, and
  `NumericRangeRule` checks the numeric ones.

  Measured across every shipped profile: two rules change, both Darwin Core's
  (depth and elevation). MIAPPE's four date comparisons are still date ranges.
  A comparison whose operand types cannot be resolved keeps the date reading it
  had.
- A profile's own identifier pattern is enforced instead of MIAPPE's. Any field
  named `identifier` or `unique_id`, in any profile, was given MIAPPE's shape —
  alphanumerics, underscores and hyphens — chosen by the field's name. DiSSCo
  identifies a specimen by a DOI, which contains `:` and `/`, so the profile's
  own pattern and the imposed one could not both be satisfied and no valid
  DiSSCo specimen could be created while identifier validation was on (#246).

  Measured against every shipped profile: only DiSSCo changes. The identifier
  patterns declared by isa, metabolights, miappe, pride and seek are identical
  to the default that was being imposed, and `seek-ready-template` declares
  none and keeps it.

### Changed
- The example route asks the facade to load a document instead of walking it
  itself. Its private copy of that walk was what made the previous entry's bug
  possible: the application could load a nested dataset and a library consumer
  could not, because only the application had the code.
  `tests/test_ui_does_not_reimplement_the_library.py` fails if a UI module
  grows its own entity-tree walk again.
- OLS is now one term source among several rather than the only one. Term
  lookup goes through a router (`metaseed.services.terms.get_term_source`)
  holding whichever adapters are configured, asked in order, with the rule that
  the first source claiming an ontology answers for it alone — otherwise a list
  someone narrowed on purpose would be silently widened again by a public
  service. `TermSource` is a Protocol, so an adapter for a service metaseed has
  never heard of conforms by having the methods, without importing metaseed.

  This reaches the interfaces, not just the library: the term picker in the UI
  and the MCP search and lookup tools built OLS4 HTTP queries themselves, so a
  vocabulary held locally could not appear in a dropdown no matter what was
  configured. `tests/test_term_sources_are_adapters.py` fails when a module
  reaches for OLS directly again.
- The entity lookup asks the endpoint the page names (`data-lookup-url`),
  defaulting to the standalone application's `/api/lookup/`. An application
  embedding these tables serves its own — the hub's is scoped to a dataset —
  and could not before, so its reference columns had no lookup at all.

## v0.32.1 (260812)

### Fixed
- An entity was exported twice: once as its own row, once as the dict still
  embedded in its parent's data. Every child appeared in the sheet twice, and
  the copy carried no parent, since only a stored row knows what it hangs from.
  The ENA example exported 12 samples where it has 6, 27 files where it has 15,
  and an analysis that appeared to belong to nothing. A copy is recognised by
  being contained in a stored row under the same parent — not by identifier,
  because entities repeat one legitimately and deduplicating on that deletes
  real rows (16 sample attributes, in the attempt before this one).
- The uniqueness rule treated an entity's first field as its identifier, which
  is what the facade falls back to when a profile declares no key. ENA's
  `File.filename` and every attribute `tag` column were flagged on every row
  that repeated by design. A column counts as a key when the specification says
  so, or when another entity references it.

## v0.32.0 (260812)

### Added
- Exported spreadsheets carry the standard, not just its column names, after
  RightField (Wolstencroft et al., 2011): a column with a declared vocabulary
  becomes a dropdown, a column that names another sheet picks from the rows
  that exist, and an identifier column objects when it repeats. The terms and
  where they came from travel in a hidden sheet, so nothing semantic is lost to
  a label.

  An ontology is documented, never embedded — NCBI Taxonomy cannot go in a
  spreadsheet and a dropdown of thousands is worse than typing — so those
  columns stay free text and are checked on import instead.

  The rules warn rather than block: a vocabulary is rarely complete, and
  someone who knows their value is right should not be locked out of their own
  spreadsheet. Whatever they accept stays coloured by conditional formatting,
  which also catches pasted values — validation dialogs never fire on a paste.

- Exported sheets are readable by the person filling them in: real Excel tables
  (so a row typed underneath inherits the banding and the dropdowns), the
  heading row and identifier column frozen, each heading carrying its
  description from the specification as a comment, columns sized to their
  content, and wrapped text.

### Fixed
- Timestamps written by the library were the machine's local time with no
  offset: a dataset's `modified` field, the same field in the file and
  filesystem repositories, and the date stamped into export filenames. A naive
  timestamp cannot be ordered against a UTC one, so "which copy is newer" was
  guesswork across a DST change or a differently configured machine. All clock
  reads are UTC, and a test fails on a naive one.

### Added
- A release gate that refuses a tag with no matching `CHANGELOG.md` section.
  Sixteen releases once shipped without an entry because the rule existed only
  as prose; it runs before the test suite, so a missing entry fails in seconds.

### Changed
- The built-in `seek` profile is described as what it is: the full model SEEK
  can represent, for exploring and visualizing an instance. Only its ISA core
  syncs and its `Project` root does not, so it is a reference model rather than
  an upload target — `seek-ready-template` is the profile to build on.

## v0.31.0 (260811)

### Fixed
- Pushing a dataset to SEEK twice created a second copy of everything. Nothing
  looked for what the previous push had made: only Sample Types were ever
  reused. Investigations, Studies, Assays and Samples are now found before they
  are created, and what was reused is reported separately from what was
  created.

  Matching is by title within the parent, because SEEK's ids stay in SEEK:
  nothing here records them. The cost is that renaming a record in the dataset
  makes the next push create a new one and leave the old behind — a rename to
  do in both places, rather than a copy of SEEK's ids to keep in step.

## v0.30.0 (2026-08-10)

### Added
- Excel import: the Import button also takes a workbook exported by metaseed,
  sniffed by content. The export writes a `_parent` column carrying the tree
  (no profile declares `parent_ref`, so the linkage must ride along), and the
  import feeds the same loader JSON uses. A workbook from a different profile
  is refused instead of importing nothing silently.
- Long optional-field sections in entity forms get a filter box (more than
  eight fields); a 43-field section becomes type-what-you-want.

### Changed
- Excel export writes every cell as text, so gene names stay names and
  identifiers keep their leading zeros. An empty scalar list exports as an
  empty cell — it exported as "0", which failed validation on reimport and
  silently dropped the whole entity.
- Profile descriptions in the new-dataset picker clamp at five lines with the
  full text in a tooltip under the title; Load Example aligns right.
- The seek sync links a material to its assay through the field the profile
  declares as a reference, not by scanning values for anything that matches.
- `_mapping` is public as `metaseed.mapping`; four adapters share it.

## v0.29.0 (2026-08-05)

### Added
- The SEEK page shows what a profile becomes **before** uploading: a browsable
  panel of the Sample Types (each expandable to its columns) that provisioning
  will create, and the Extended Metadata the Investigation, Study and Assay
  records carry. It refreshes live with the profile/version dropdowns and writes
  nothing to SEEK. Backed by `metaseed.seek.preview.build_model_preview`, read
  from the same plan `Provision` executes so it cannot drift.
- `seek-ready-template`, a minimal ISA-shaped built-in profile
  (Investigation → Study → Assay → Sample) whose datasets upload to SEEK with
  nothing left behind, plus a guide on authoring SEEK-ready profiles.
- A study's data files sync to SEEK as one remote data file linking to their
  common base URL, so externally hosted files (e.g. an S3 bucket) are recorded
  by filename without uploading bytes. `DataFile` is a valid SEEK role.
- The SEEK page can provision a chosen profile **version**, not only the latest.
- A dataset can be imported into SEEK through its FAIR Data Station importer,
  driven from the UI.

### Changed
- The SEEK page describes provision, sync and export in the user's terms, and
  explains that "Project" is a project on the SEEK server.
- A sync that leaves entities behind now warns instead of reporting plain
  success, and says once, actionably, why each entity was skipped.
- A plain `list` field is sent as the single string SEEK's Text attribute
  expects, and every synced sample is given a title SEEK will accept.
- The property URI is percent-encoded wherever a dataset is exported, not only
  where it is provisioned; a gate keeps provisioning and export naming a field
  identically, so a sample is never rejected for a URI the two sides disagree on.

## v0.28.0 (2026-08-04)

### Changed
- The built-in profile is named for the platform it describes rather than its
  ontology: `jerm` became `seek`.
- A dataset keeps loading under the profile name it recorded, so renaming a
  built-in profile does not orphan datasets authored against the old name.

## v0.27.0 (2026-08-04)

### Fixed
- A property URI is built so a field name cannot break it (a name containing a
  space produced an invalid URI and SEEK rejected the sample type); the refusal
  reason SEEK returns is now reported instead of a bare failure.
- A profile is listed once whatever case its directory carries.

### Changed
- A specification's help text is shown rather than hidden in a `title`
  attribute, and the help cursor is offered only where there is help.

## v0.26.0 (2026-08-04)

### Added
- `tests/test_public_api.py` gates the public surface: the stable-surface table
  in `docs/specification/api-contract.md` is compared against `metaseed.__all__`
  in both directions, every promised name must resolve, and the documented
  import example must run.

### Changed
- An incomplete entity can be saved, and the editor reports what it still needs
  instead of refusing the save. Required fields drive validation reporting, not
  whether a record can be stored.
- The empty canvas accepts the double-click it invites, and the field form is
  reusable with its checkbox layout fixed.
- The core no longer imports the web application. Importing
  `metaseed.cli.migrate` used to construct the FastAPI app; `get_datasets_dir`
  moved to `metaseed.paths`, `metaseed.ui` resolves the app lazily, and the MCP
  host's dependency on the shared editing session is declared once in
  `metaseed.agent.mcp.ui_session`.
- The dataset factory is supplied to the UI rather than discovered by it.
  `metaseed.ui.datasets` no longer imports the MCP server to find out whether an
  agent session is running; `set_factory` is called by whoever composes the
  application.
- `DEFAULT_DATASETS_DIR` was hardcoded to `~/.local/share` in two modules, so
  `XDG_DATA_HOME` was honoured for specs and ignored for datasets. Both now
  derive from the same base.

### Removed
- `UniquenessRule` and `EntityReferenceRule` from the validation engine, with
  the `available_refs` parameter that fed the latter. Neither could ever fire:
  a fresh engine is built per record, and the reference rule was constructed and
  then discarded. Uniqueness and reference integrity are enforced by
  `DatasetValidator`, which is unchanged.
- The dissco 0.4 rule `scientific_name_required`, which duplicated a field
  already declared `required: true` and whose `condition: required` could never
  pass.

### Fixed
- A save callback bound `auto_save` when the session was built, so a test that
  patched it afterwards still ran the real one and wrote to the user's datasets
  directory.

## v0.25.0 (2026-08-02)

### Added
- `import_from_database` MCP tool and a matching web route, so a public record
  can be imported by accession from the editor as well as from a tool call.
  Both go through one seam in `metaseed.adapters`.

### Changed
- Coverage is measured once per release instead of on every pull request, where
  it trebled the gate for a number nobody reads mid-review. The threshold still
  blocks a publish.
- Validating an extracted record now runs the profile's cross-field validation
  rules, not only the record's own field constraints. `validate_extracted`
  previously ignored `validation_rules` entirely, so a profile rule could not
  reject a record on that path. Rules needing sibling records (`uniqueness`) or
  a child collection (`cardinality` over children) still cannot be evaluated on
  a single record and are skipped rather than reported as passing.

### Removed
- `tests/fixtures/isa_examples/`, referenced by nothing and carrying real
  researcher names, institutional addresses, telephone numbers and ORCIDs.
  `tests/test_no_real_personal_data.py` gates the parts a test can decide.

## v0.24.0 (2026-08-01)

### Added
- The twelve declarative field markers are settable from the MCP spec tools:
  `codename`, `ontologies`, `unique_within`, `dcat`, `owns`, `is_identifier`,
  `is_label`, `example`, `options`, `unit`, `label`, `tier`. The set is derived
  from `FieldSpec.model_fields`, so it cannot drift from the schema. An unset
  marker is absent from the serialized spec rather than written as `false`, so
  the content hash does not record whether one was toggled.
- `SpecBuilder.warnings()`, advisory findings that never affect validity, and a
  `warnings` key on `spec_validate`. The first warning reports an entity whose
  identifier is not declared and whose inferred one is an optional free-text
  field. It finds five such cases in shipped profiles (issue #212).

## v0.23.0 (2026-07-31)

### Added
- `metaseed.deprecation.deprecated`, giving the documented deprecation policy a
  mechanism: it warns at the caller's line, requires a removal version, and
  appends the notice to the docstring. Deliberately absent from `__all__`.
- `MetaseedClient.load(data, on_skip=...)` and the public `SkippedNode`.
  Permissive loading is opt-in and the callback both enables it and receives the
  reports, so it cannot be switched on without somewhere for them to go.

### Fixed
- A nested entity whose parent node carried no `id` was flattened into a root,
  because recursion passed the stored id rather than the one the node was
  created under.
- `SpecBuilder.validate()` now reports a `list` or `entity` field with no
  `items`, which previously validated clean. `items` naming a primitive is
  still valid.

### Changed
- Pull requests run the fast gate (lint, format, types, tests). Before this the
  workflow ran only on tags, where the job skips itself, so branch protection
  required a check that could never report.

## v0.22.1 (2026-07-31)

### Added
- `metaseed migrate-specs`, repairing profile versions the 0.22.0 validator made
  unloadable. Dry-run by default; normalisation is explicit (strip a leading
  `v`, pad a single integer, drop a pre-release suffix, truncate three or more
  components and flag it lossy), and anything underivable is reported rather
  than guessed.
- `SpecBuilder.update_field_constraints(entity, field, *, clear=(), **values)`,
  merging constraint edits. Constraints are one object holding eight named
  values, so assigning it wholesale silently dropped the seven not supplied.

### Fixed
- The loader created an empty `Constraints` object when a rule applied nothing
  to a field, so identical content hashed two ways and broke the round-trip
  stability the content hash promises.

## v0.22.0 (2026-07-31)

### Added
- Profile versions are validated as `MAJOR.MINOR` and mean something: MAJOR
  signals that datasets valid under the previous version may fail.
- `content_hash` and `short_hash` on `ProfileSpec`, a canonical fingerprint that
  is stable across a YAML round trip and unaffected by key order, so two specs
  claiming the same name and version can be told apart.
- `compare_specs` and `required_bump`, classifying every change between two
  specs as breaking or compatible, and the `spec_compare` MCP tool.

### Changed
- Publishing is gated on a fresh-resolution install of the built wheel. The
  locked test suites cannot see resolver drift: mcp 2.0.0 satisfied an unbounded
  `mcp>=1.0.0` pin and removed `mcp.server.fastmcp`, so every fresh install of
  v0.21.0 crashed while CI stayed green.

### Note on earlier releases

Entries for v0.13.0 through v0.21.1 were not written at the time and are not
reconstructed here; `git log` between the tags is the record for those versions.

## v0.21.1 (2026-07-30)

### Fixed
- `mcp` is bounded below 2.x. Version 2 removed `mcp.server.fastmcp`, which the
  MCP server imports directly, so an unbounded requirement let a fresh
  resolution install a version that breaks on import. Lockfile-based suites
  stayed green while fresh installs failed.

## v0.21.0 (2026-07-30)

### Changed
- The spec-builder graph core was extracted into a reusable factory so the hub
  can consume it instead of maintaining a fork.

## v0.20.1 (2026-07-30)

### Fixed
- Reference edges name both connected fields; entity-only edges hid the join
  columns.

## v0.20.0 (2026-07-30)

### Added
- MCP agents can link spec entities into a tree. A flat spec validates but is
  unusable, so the tools now express parent-child nesting.

### Fixed
- BrAPI transport failures are translated into the mistake they usually are,
  rather than surfacing as a bare connection error.
- A selenium test waited for presence rather than visibility, so the hidden
  seek-role select made it flaky.

### Changed
- Documented that validation feedback is spec-derived and must not be
  re-implemented, and corrected the `ValidationResult` truthiness claim.

## v0.19.0 (2026-07-27)

### Fixed
- Every PRIDE record is imported as its own entity, and `doi`, licence and
  experiment types are no longer dropped.

## v0.18.0 (2026-07-27)

### Added
- The DCAT record is offered as an export for every profile, and PRIDE and
  MetaboLights datasets describe themselves in DCAT. A publishing platform can
  bind a card to where it serves the dataset; a repository accession is recorded
  as provenance rather than as the card's identity.

### Changed
- MCP tools serve the caller's session rather than the process default. A host
  passes the resolver that identifies its caller, and the MCP context has a
  scope a host can bind without a shared singleton.

## v0.17.0 (2026-07-27)

### Added
- `MetaseedClient.from_facade`, wrapping an existing facade.
- A normative Specification section in the docs, and a package front door that
  describes metaseed as multi-standard rather than MIAPPE-only.

### Fixed
- `ValidationIssue.field` is the bare field name, and the issue carries
  `entity_id`.
- The shared dataset factory is reused instead of a fresh one being created.

## v0.16.1 (2026-07-26)

### Added
- `AsyncSpecDraftStore` port with an in-memory default adapter.

### Fixed
- An entity's `is_identifier` field is respected when auto-creating
  back-references, and a child's parent reference is auto-filled from
  `parent_id`.
- PRIDE datasets held as child nodes export, not only inline-authored ones.
- Sample characteristics are emitted in the ISA-Tab study table.

### Removed
- Real personal data from examples and fixtures; tests are no longer packaged.

## v0.16.0 (2026-07-25)

### Fixed
- `AsyncDatasetRepository`, the async half of the storage contract, was restored.

## v0.15.0 (2026-07-24)

### Fixed
- The open dataset stays selected when reloading for a poll.

## v0.14.0 (2026-07-24)

### Added
- A declarative plugin capability model (`Action` plus UI surfaces).
- Import of Samples, Metabolites and DataFiles from ISA-Tab.
- Spec field markers for owning parent, declared identity and field metadata.

### Changed
- Adapter exports are offered on the dataset page, not only after a save.
- Publishing to PyPI happens on a version tag via trusted publishing.

## v0.13.0 (2026-07-23)

The release that introduced the SEEK integration.

### Added
- `metaseed[seek]`: a JSON:API client, Controlled Vocabulary and idempotency
  lookups, two-phase provisioning (create the model, then sync data), a SEEK
  export page, per-adapter plugin configuration, and FAIR Data Station Turtle
  RDF for SEEK's native import. Entity **role** became a SEEK-specific model
  constraint in the Spec Builder.
- A plugin registry with a feature switch and a Plugins UI page.
- PRIDE SDRF-Proteomics sample-to-data export, the MetaboLights Metabolite
  Assignment File (MAF), and CV-term compliance validation for both.

### Fixed
- Security: Excel formula injection in the UI export, a ReDoS on the MCP
  validate path, and path traversal via spec name/version and dataset names.
- Validation enforced rather than silently dropped: Pydantic constraints on
  every validation path, rule-level enum/pattern/range constraints, declared
  uniqueness across records, unknown rule types rejected, a required field set
  to `None` treated as missing, and files declaring an unknown entity `_type`
  rejected instead of failing open.
- List-cardinality rules are satisfied from created children.

### Removed
- Unbuilt async dataset infrastructure (no implementations, no callers) and
  dead symbols.

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
## v0.3.7 (2026-05-26)

### Changed
- Fix Selenium test to use correct btn-new-dataset testid
- Refactor facade and UI components for better separation of concerns
- Add files field to ENA Run entity
- Refactor entity storage to use ProfileFacade as source of truth
- Fix loading to link children via parent's nested arrays
- Auto-fill reference fields when single parent exists
- Add study_ref field to ENA Sample for parent auto-detection
- Add lenient loading to handle schema evolution
- Add edge case tests for MCP data integrity
- Fix MCP parent linking duplication and add schema validation tests

## v0.3.6 (2026-05-21)

### Changed
- Remove embedded files from Run, use File.run_ref reference instead

## v0.3.5 (2026-05-21)

### Changed
- Add run_ref field to ENA File entity for parent reference

## v0.3.4 (2026-05-21)

### Changed
- Add version to footer and fix spec builder navigation

## v0.3.3 (2026-05-21)

### Changed
- Use first field convention for entity labels
- Revert is_identifier explicit marking in favor of convention
- Add is_identifier to spec builder and documentation
- Use field-level is_identifier instead of entity-level attributes
- Add spec-defined identifier_field and label_field support
- Style reference edges with distinct orange color
- Support string reference fields in graph (ENA sample_ref pattern)
- Use get_identifier helper instead of hardcoded field names
- Fix graph identifier mapping to check multiple fields
- Handle list and single reference fields in graph edge building
- Normalize reference fields to store IDs instead of embedded objects
- Disable graph polling since UI and MCP share state
- …and 20 further changes; see git history.

## v0.3.2 (2026-05-20)

### Changed
- Update dataset repository docs with async interface examples
- Add AsyncDatasetRepository and AsyncDatasetManager for database backends
- Add dataset repository architecture documentation

## v0.3.1 (2026-05-20)

### Changed
- Add tests for dataset DI refactoring
- Export DatasetRepository classes from repositories module
- Update MCP dataset tools to use DatasetManager
- Update API routes to use DatasetManager directly
- Refactor datasets.py to use DatasetManager
- Add DatasetManager with dependency injection support
- Add DatasetRepository ABC and FilesystemDatasetRepository

## v0.3.0 (2026-05-20)

### Changed
- Add MCP tools, JS modules, migration CLI, and refactor code
- Fix get_field_spec: check hasattr before accessing example
- Extract nested items from tree children for MCP-created entities
- Add validate_entity to validators module for shared validation
- Fix run_server to accept transport parameters from CLI
- Remove in-process MCP mounting, keep button-only approach
- Fix MCP API routes to use MCPServerManager for port 8001
- Fix MCP server mounting - actually mount SSE app at /mcp
- Remove trivial and redundant tests
- Reorganize UI helpers into subpackage
- Update architecture overview with MCP server and agent layer
- Consolidate label derivation logic to single implementation
- …and 20 further changes; see git history.

## v0.2.4 (2026-05-12)

### Changed
- Fix merger to include REMOVED fields from source profiles
- Remove orphaned isa-miappe-combined tests (profile was removed in 21e4d0e)
- Configure pre-commit to lint entire codebase
- Fix ruff linting error in test_examples.py
- Change spec builder default version to 0.1, remove fallbacks
- Fix get_root_entity_types to use facade's injected spec
- Add dependency injection to ProfileFacade for custom spec loading

## v0.2.3 (2026-05-08)

### Changed
- Remove isatools dependency (no longer used)

## v0.2.2 (2026-05-08)

### Changed
- Document REST API endpoints and Facade API
- Remove ISA importer feature
- Complete documentation for recent changes and missing profiles
- Refactor codebase based on code review
- Refactor test_examples.py for improved code quality

## v0.2.1 (2026-05-07)

### Changed
- Complete all examples with full entity list population
- Remove cropxr and isa-miappe-combined specs from built-in specs

## v0.2.0 (2026-05-07)

### Changed
- Add comprehensive example validation tests and fix field type mismatches
- Fix linting configuration for pre-commit consistency
- Fix API route to allow single profile for explore mode
- Add configurable base_url to templates for reusability
- Rename /merge/ routes to /explore/ and add get_templates_dir
- Export SpecPersistence and SpecProvider from metaseed.ui
- Extract reusable UI components with abstract interfaces
- Prevent saving specs with built-in spec names
- Restructure header: Logo | Nav | Breadcrumb
- Rename Explore to Explorer in nav
- Add explore mode to compare page
- Refactor CLI and add user feedback improvements
- …and 88 further changes; see git history.

## v0.1.0 (2026-04-24)

### Changed
- Add automatic versioning from git tags
- Improve code architecture with shared utilities and type hints
- Refactor routes.py into domain modules and encapsulate model context
- Complete DiSSCo spec with TombstoneMetadata entity
- Fix DiSSCo spec: mark modified field as required
- Add DiSSCo spec and improve ISA example and export
- Improve spec builder UI and field validation options
- Add interactive spec builder with ERD visualization
- Update validators, routes, and examples
- Add codename field to FieldSpec schema
- Add MIAPPE 1.2 specification and example
- Fix hierarchical graph levels with explicit level tracking
- …and 151 further changes; see git history.
