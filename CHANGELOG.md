# Changelog

## [Unreleased]

## v0.44.0 (260827)

### Added
- **The explorer shows everything a profile says.** Clicking an entity now
  lists its description and ontology term, every attribute each field has set
  (description, constraints, unit, example, identifier/label markers, tier,
  ISA and SEEK markers) and the validation rules that apply to it; the sidebar
  lists every rule of the base profile. A field shows only what it has set.

### Fixed
- **A profile pushed to the hub is a private draft, not a publication.** The
  hub's *published* means visible to every user, and the first release of the
  push published straight away — putting an author's profile in front of
  everyone without them choosing it. A push now lands as your draft (a revised
  push updates it); *Publish* asks explicitly and confirms; *Unpublish*
  withdraws one you published. Needs metaseed-hub 0.42 or later.
- **`settings.json` is written readable only by its owner.** It holds a SEEK
  API key and now a hub access token in plain text, and the default mode let
  every account on the machine read them. Existing files are tightened on the
  next write; tighten one now with `chmod 600`.
- **A hub too old for the exchange is told apart from a wrong URL.** The
  deployed hub answers 404 for `/api/me` while being a perfectly real hub, and
  the check said "not a metaseed-hub. Give the hub's base URL" — sending the
  reader after a URL that was right. It now reads `/api/health`, which every
  hub answers, and names the version that needs updating.
- **`metaseed hub profiles` says draft or published for each entry** instead of
  calling everything on the hub published.

## v0.43.0 (260826)

### Added
- **The CLI reaches everything the MCP server and the web interface reach** (#263).
  Ten new command groups — `dataset`, `entity`, `profile`, `ontology`, `extract`,
  `spec`, `seek`, `hub`, `plugin`, `dcat` — each delegating to the same library
  functions the routes and the tools call. A dataset command names the dataset it
  acts on, loads it, changes it and writes it back, since a terminal has no
  editing session; a specification draft is a file for the same reason. Output is
  JSON, so a script reads what a person reads. The 15 existing flat commands are
  unchanged. *Capability parity* in the documentation records which command,
  tool and route serve each capability, and `tests/test_capability_parity.py`
  fails when an MCP tool or a state-changing route arrives without a command, or
  when the table names one that does not exist.
- **Datasets and profiles push to a metaseed-hub and pull back** (#262). *Settings → Plugins → Metaseed Hub* takes the hub URL and a personal access token; the check names the account and tenant. On the datasets overview every dataset has *Push to hub* — a plan first (create, identical, or what differs), sent only when confirmed, a differing hub dataset replaced only when chosen — and *Pull from hub* lists your hub datasets; a pulled one that differs from a local dataset of the same name lands beside it as `<name>-hub`. The explorer's *Push / pull profiles* publishes a user-local profile on the hub under its version-bump gate and pulls published specifications into the user specs directory, never over a differing local one. Each dataset records where it last went or came from. See *Pushing and pulling with metaseed-hub*.
- **The entity list and the graph are two views a dataset switches on and off independently.** The dataset toolbar has a *List* and a *Graph* toggle (at least one stays on); whatever is on shares the full width, so on a wide screen the table and the graph sit side by side. The graph panel has *Fullscreen* (the graph on the whole screen, Esc leaves), *New window* (`/graph`) and *Close*. The choice is remembered per browser.
- **The profile explorer shows controlled vocabularies.** A field with an enumerated vocabulary is marked `[N terms]` on the node and lists its terms in the entity panel; *Show/Hide* use the profile's display name.
- **A profile can describe the ISA chain against templates already installed
  on the SEEK instance** (#256, #257, #258). An entity that names its
  installed ISA Template (`seek.template`) and tags its fields (`isa_tag`,
  which now includes `input`) is *template-bound*: its own fields are the
  Sample Type's columns, its title-tagged field the title attribute, and its
  ISA level follows from that tag — `source`, `sample`, `other_material`
  (`assay - material`, new) or `data_file`. The sync then places samples by
  level rather than by tree position, creates one SEEK Assay per assay-level
  entity under a profile Assay (SEEK gives an Assay one Sample Type, so a
  material and a data file are two chained Assays in the stream), resolves a
  predecessor named through an `Input` field by title, and writes the input
  link under SEEK's real key, `Input (<predecessor's title attribute>)`.
  *Download ISA Templates* renders such entities faithfully, so the same
  profile can provision a fresh instance. The untagged, nested shape
  (`seek-ready-template`) is unchanged and remains the live regression gate.
  See *Two ways a profile can describe the chain* in the ISA-JSON compliance
  page.
- **Study and Assay field values are pushed as Extended Metadata** (#259).
  An entity names its installed Extended Metadata Type
  (`seek.extended_metadata`); a prefix group
  (`seek.extended_metadata_groups: {site: location}`) fills a nested type
  from the flattened `site_*` fields. Fields the type lacks are reported, a
  type the instance lacks is an error. Verified live: a CropXR phenotyping
  Study reads back with its nested `location`, `experimental_design` and
  `growth_facility`.
- The SEEK page reflects a template-bound profile: the preview lists each
  entity's installed template, ISA level and per-column tag (from the plan the
  sync builds the types from), and step 1 becomes **Set up Controlled
  Vocabularies** — provisioning no longer creates profile-named Sample Types
  the sync never uses beside the templates.
- An Extended Metadata attribute that holds a reference to a SEEK record
  (`Registered Data file`, `Registered Sample`, ...) is reported and not sent:
  a plain value there made SEEK refuse the whole Study or Assay with an HTML
  422 naming nothing. The SEEK Assays a profile Assay becomes are named after
  the template each is built from (`<assay> (CropXR phenotyping data file)`)
  rather than after metaseed's entity names.
- An `Input` field may declare which entity it references (`reference:
  ObservationUnit`); the Sample Type then links to that entity's type instead
  of the level before it, and assay-level entities are grouped into the linear
  chains SEEK can hold — every chain beyond the first becomes its own assay
  stream, because SEEK splices an assay whose input another assay in the
  stream already takes in front of it. This is how an "assay with data file"
  (input: the study sample) coexists with a material → data file chain under
  one profile Assay.
- A value left out of a Study or Assay that did reach SEEK (a field the
  Extended Metadata Type lacks, or a record-reference attribute) is reported
  under *Values not sent* on the SEEK page, in `SyncResult.notes`. It used to
  be listed as a skipped entity, so the page declared the copy incomplete.
- **Synced Sample Types are the installed template, column for column**
  (#261). Fields carry the exact SEEK column where the field type cannot:
  `seek_attribute_type` (`ENA custom date`, `Text`, `Registered Data file`,
  `Registered Sample List`), `seek_controlled_vocab` (the instance vocabulary
  SEEK created when the template was populated, resolved by title at sync
  time — provisioning makes no copy of it, and an absent one is an error
  naming the column) and `seek_cv_free_text`; every attribute carries its
  `template_attribute_id`. `metaseed seek-import-templates profile.yaml
  templates/*.json --write` derives the template-bound entities from the
  template files, keeping what only the profile knows; the gate is that the
  derived entity renders back to the template attribute for attribute.
- A `Registered Data file` column or Extended Metadata attribute is filled by
  registering the file: its URL becomes a remote SEEK DataFile (once per URL)
  and the column receives that record's id, which is what SEEK stores there.
  A value that is not a URL, or one SEEK cannot reach when registering, is
  reported under *Values not sent* rather than failing the record.
- **Load Example** works for profiles installed under the user data dir: the
  loader looks in `<user data dir>/examples/<profile>/<version>/` as well as
  the packaged examples, so a user profile can ship example data beside its
  spec. It looked only in the package before, and the picker offered no
  example for any user profile.
- The SEEK page offers **Download ISA Templates (.json)** for the selected
  profile and version. The sync's missing-Template error has always pointed at
  "the SEEK page"; the page now actually has the button. A SEEK administrator
  uploads the file under *Templates → Populate Templates*, once per profile and
  version.
- `SyncResult.sample_types` records the Study-owned Sample Types a push
  created. SEEK does not delete them with their Study — they stay behind as
  orphans — so a caller cleaning up after itself needs their ids.
- The documentation footer discloses that the docs are AI-generated (EU AI Act
  transparency), gated by `tests/test_docs/test_ai_disclosure.py`.

### Changed
- The profile explorer shows a field's controlled vocabulary: the node lists
  `[N terms]` beside the field, and the entity panel opens the terms. The
  Show/Hide labels in compare mode use the profiles' display names, as the
  selects do.
- The graph panel has its own bar: **Close**, **Beside / In place** (beside
  the list is the default from 1400px wide, remembered per browser) and
  **New window**, which opens the graph alone at `/graph` for a second screen.
  The Graph button lives in the dataset toolbar the graph used to hide when
  it took the list's place, so the panel needed its own way back.
- The dataset toolbar is a row of its own under the dataset title, grouped
  (validate · graph · DCAT | exports | import | back), instead of squeezing
  the title beside a long run of buttons.
- Validate, Graph, DCAT and the adapter exports moved from the global header
  into the open dataset's toolbar. Every one of them acts on the dataset that
  is open, so they sat in the header on pages (Settings, Spec Builder, the
  datasets overview) with nothing to act on.
- Dependency updates come from **Renovate** on `config:best-practices`
  instead of Dependabot. Dependabot cannot update `uv.lock`, so its PRs left
  the lockfile CI installs from untouched; Renovate regenerates it, pins
  Actions to digests, runs weekly lock-file maintenance, and groups Python
  and Actions updates into one PR each, as before. Security alerts are
  unaffected (a repository setting, not the updates config).
- *Sync to SEEK* shows a progress bar. The push runs in a background thread
  and reports every placed node (`on_progress` on `sync_dataset_to_seek`);
  the page polls `/seek/sync/progress` each second and the result replaces
  the bar when the push finishes. A push used to hold the request open for
  minutes with no sign of life.
- Saved datasets are listed newest **created** first, and each card shows its
  creation date beside the modification date. A dataset records when it was
  first saved (`created`) and keeps that on every later save; the list used to
  order by last modification, so editing an old dataset moved it to the top.
  A file saved before this was recorded sorts by its modified time.
- The *Sync to SEEK* button sits beside the project select, not beside its
  label: the sync form now bottom-aligns like the provisioning form.

### Removed
- The in-app HTTP MCP server: the header's MCP button, `/api/mcp/status`,
  `/api/mcp/start`, `/api/mcp/stop` and the subprocess manager
  (`metaseed.agent.mcp.manager`) that spawned a server on port 8001. MCP is
  used over stdio (`metaseed mcp`, configured in the agent); HTTP transport is
  the hub's. `MCPServerManager`, `MCPServerStatus` and `get_mcp_manager` are no
  longer importable from `metaseed.agent.mcp`.

### Fixed
- **A hub dataset whose name the local store cannot hold no longer breaks the
  pull listing.** A name with a space is not one a dataset file can have, and
  asking the repository about one raised instead of answering; the listing now
  asks through `local_counterpart`, which reports no counterpart for a name that
  could never be stored.
- **Tests no longer inherit each other's generated models** (#255). Models are cached
  globally by `profile:version:name` so validation can resolve nested entities;
  two tests building the same profile name from different specs handed each
  other the wrong model, and the second saw "Extra inputs are not permitted" for
  a field its own spec defines. The registry is cleared between tests, and
  `tests/test_models_are_not_shared_between_tests.py` fails if it stops being.
- **Two profile Assays in one Study no longer share an assay stream.** SEEK splices assays in a stream into one line, so LC-MS, GC-MS and NMR assays of the same samples were chained after each other; every profile Assay after the first in a Study is now its own stream, as a second chain under one Assay already was.
- **The test suite no longer touches the user's saved datasets.** Tests that
  saved, listed or deleted datasets through the app used the real
  `~/.local/share/metaseed/datasets`: test datasets appeared in a running UI,
  and a run's cleanup deleted the user's own datasets. Every test now gets a
  private directory (`METASEED_DATASETS_DIR`, set by an autouse fixture that
  also rebinds the dataset factory), gated by
  `tests/test_tests_never_touch_the_user_datasets.py`. Datasets tests
  create are named `test-<what they are>`; the fixture refuses any other
  name on the write.
- The SEEK page's inline status blocks (progress, results, errors) are static
  boxes, not toasts: they carried the toast class, which is fixed-position and
  animated, so the polled progress bar slid in as a new toast every second.
- **Pushing a dataset again updates what the first push created** (#260).
  Every re-push used to create a second Investigation: the `/investigations`
  index carries no project relationship, so the reuse lookup never matched.
  A title match is now confirmed against the item, and a reused Assay is
  recorded the way a created one is (identifier, protocol, Sample Types), so
  the materials of a second push find it, and a data file registered by an
  earlier push is found by title instead of registered again. A second push
  of the live test dataset creates nothing and reports everything as reused.
- **A pushed dataset now exports from SEEK as ISA-JSON.** The last gap was not
  in the structure: `SeekClient._send` attached the API token only on some code
  paths, and SEEK serves an unauthenticated `export_isa` the anonymous view —
  `200 OK` with every assay stream silently dropped whose samples the public
  cannot see. The token now rides on every request the client sends, and the
  live export check (`test_a_pushed_dataset_is_exportable_as_isa_json`) is a
  passing test instead of a strict xfail.
- A Sample nested under an Assay goes in that Assay's own Sample Type, linked
  to it. It used to land in the Study's Source type with no ISA link, where
  nothing walking down from the Investigation could reach it. A declared assay
  reference still wins over tree position.
- A Sample whose material chain never reaches an Assay link is reported in
  `SyncResult.unlinked` instead of being counted as placed and said nothing
  more about. It is still created; the report says why a re-import will not
  find it.
- The importer no longer reads assay streams back as Assays (the stream is
  sync plumbing, and every round trip doubled the assay count), and it follows
  an assay material's input links back through the ISA chain, so a pushed
  dataset returns as nested `Source -> Sample -> AssayMaterial` with its field
  values instead of losing the Study-owned levels entirely.
- The sync's Sample Type lookups retry briefly when SEEK serves a stale read
  right after a create (its authorization tables are maintained by background
  jobs). One stale read used to turn every Source under a new Study into an
  unlinked sample.
- The live-test teardown deletes assay streams and Sample Types too. Streams
  are assays SEEK will not delete a Study over, so every run left its whole
  tree behind (403), and the leftovers poisoned later runs through the sync's
  reuse-by-title.
- The graph embedding guide names the element ids `graph.js` actually reads.
  It listed `graph-spring-length` and `graph-node-distance`, which the script
  never looks up, so a host following the contract got spacing controls that
  silently did nothing. A gate now fails when the guide promises an id the
  script does not read.

## v0.42.0 (260817)

### Removed
- The `isa-miappe-combined` profile no longer ships with the package. It was
  added in 0.38.0 while documenting it (#49): the issue asked for a docs page
  for a profile that existed only in the author's user-specs directory, and
  shipping it was a larger step than the issue called for. It remains a
  user-defined profile — an installed copy under
  `~/.local/share/metaseed/specs/` still loads and is still listed — but
  `list_profiles()` from a fresh install no longer offers it, and neither
  version (0.1, 0.2) is packaged.

  A profile that was both shipped and locally edited also had two homes, and
  that is what hid a defect during the 0.38.0 release: the packaged 0.2
  examples carried a field the profile had deleted, invisible locally because
  the user copy shadowed them.

## v0.41.0 (260817)

### Removed

- The `POST /api/compare` and `POST /api/merge` endpoints. They duplicated
  what `/explore/compare` and the explore merge routes serve, with divergent
  parsing and error contracts, had no UI surface, no tests, and no caller in
  metaseed or metaseed-hub. The explore routes are the supported surface.

**Importable names that no longer exist.** Each had no caller in metaseed or
metaseed-hub (checked), but an outside consumer importing one will fail at
import, so they are listed rather than buried under "Fixed":

- `metaseed.models.ModelNotFoundError` — never raised by anything;
  `get_model` reports an unresolvable entity with `SpecLoadError`, so catching
  it accomplished nothing.
- `metaseed.logging.get_logger` — a no-op wrapper around
  `logging.getLogger(__name__)`, which the module's own docstring names as the
  pattern to use. Replace calls with the stdlib one.
- `metaseed.repositories.file.DEFAULT_DATASETS_DIR` — a duplicate of the
  constant in `repositories.filesystem_dataset`, which is the one that is
  read; import it from there.
- `RateLimiter.acquire` (async) in `metaseed.services.ontology` — no
  production caller; `acquire_sync` is what the adapter uses.
- `metaseed.api.__all__` no longer lists `app`. The name had already been
  removed, so `from metaseed.api import *` was raising AttributeError.

**Moved:** `SEEK_ROLES` now lives in `metaseed.seek.roles`, beside the
exporter that honours it, instead of `metaseed.specs.schema`. It had drifted
from the exporter's own class mapping — declaring `role: Source` was rejected
at load though the exporter maps it, while `DataFile` was accepted and is not
a JERM class. Import it from `metaseed.seek.roles`. The two lists are
deliberately still different sets; reconciling them changes which profiles
load and needs its own measured change.

### Fixed
- A profile comparison reports a value set in one profile and absent in the
  other. Both difference checks filtered `None` out before counting distinct
  values, so an ontology term, description or display name present on one side
  and missing on the other collapsed to one value and read as agreement.
- A merge applies the strategy it was given to MODIFIED fields, not only to
  CONFLICT ones. The comparator reserves CONFLICT for structural disagreement
  (type, required, items, constraints), so a field differing on description,
  example or label always took the first profile whatever the caller chose.
- Resolving a constraint conflict no longer takes the whole merge down. The
  comparator names such a conflict `constraints.<name>`, which was written as
  a top-level key into a model that forbids extra fields.
- A generated back-reference does not duplicate an existing field name. The
  check looked only at `reference`, so a target already carrying a plain field
  of that name got a second one, and nothing rejects duplicate field names.
- `FieldForm.to_field_spec` re-validates what it built. It populated the spec
  by attribute assignment, which pydantic does not validate, so an unknown
  `isa_tag` reached the saved YAML and failed only on load-back.
- The spec-builder routes go through the library's guards: a root entity that
  names no entity is refused (`SpecBuilder.set_root_entity`), and a duplicate
  rule name is reported instead of appended (`SpecBuilder.add_rule`). Both
  guards existed; the routes assigned and appended around them.
- The MCP tools advise what `create_entity` accepts. Three built their answers
  from `nested_fields` while the repository validates a parent-child pair
  against `child_fields`, which honours the spec's `owns:` markers — ISA 1.0
  uses them in 33 places, so the two disagreed for 13 entity types.
  `create_entity` suggested creating a `Comment` under an Investigation,
  `get_profile_relationships` (which the server instructions name as the
  authority on the hierarchy) listed child types that cannot be created, and
  `validate_relationships` warned that impossible links were missing.
- `create_dataset` reports the profile's root entity instead of `null`. It read
  `facade._spec.root_entity`, which is populated only when a caller passes a
  pre-loaded spec, so the documented field was null on every real call — while
  the server instructions tell agents to add entities root-first.
- The profile comparison report escapes the spec content it renders. Every
  value — entity and field names, descriptions, patterns, examples, profile
  ids — was interpolated raw into a page served as `text/html`, and profiles
  are not all first-party: comparing one carrying `<script>` ran it in the
  reader's browser.
- Starting the MCP server no longer kills whatever holds its port. Any
  listener reported by `lsof` was sent SIGTERM and then SIGKILL, from an
  unauthenticated local route, so a click could stop an unrelated dev server
  or tunnel. The existing `_check_mcp_responding` check now decides: an orphan
  of ours is still cleaned up, anything else is reported and left alone.
- A rejected payload no longer destroys the dataset it failed to replace.
  `_load_tree` cleared the store first, so in strict mode a malformed node
  aborted the load after the caller's data was already gone — the very thing
  `load()` guards against for an empty payload. The tree path now snapshots
  and restores.
- A child survives a reload under a parent that has no identifier value,
  routine for the drafts the UI persists. `to_dict` emitted a parent link only
  as `_parent_unique_id`; where the parent had no identifier there was no link
  at all and the children became roots. The node id is written only as a
  fallback, so parent links still resolve by identifier wherever there is one.
- An owned `type: entity` nested field keeps its direction on reload.
  `linking.linked_reference_value` writes a scalar for such a field but reload
  read only lists, so the field was never linked there and the reference pass
  then linked it backwards — isa's `Process.executes_protocol` came back with
  the Protocol as parent and the Process as its child.

### Changed
- ADR 005's second decision — which parent field references a child of a given
  type — is made only in `facade/linking.py`. It had five other homes
  (`agent/mcp/tools/entities.py` twice, `api/validation.py`, `pride/export.py`,
  `ui/helpers/entity_helpers.py`), and one of them inverted the mapping, which
  takes the LAST matching field where linking.py takes the first: a parent
  declaring two nested fields of one child type grouped its children under the
  wrong table. The gate test claimed to catch a second home but scanned for a
  single string covering the other decision only; it now parses each module and
  fails on the selection pattern itself.
- Cross-record uniqueness moved out of `validators/dataset.py` into
  `validators/uniqueness.py`: the rule type, the profile-to-rules resolution,
  the checker and its predicate selection. The tree walk stays with the
  validator and is passed in, so the checker does not carry a second copy of
  it. `dataset.py` was 1018 lines against the project's 1000-line limit.

### Added
- `httpx` is declared as a runtime dependency. It is imported at module level
  by the MCP ontology tools, which the server imports at import time, but
  reached the environment only through `mcp`'s own pin — the transitive
  arrangement the project rule forbids.
- Every shipped requirement carries an upper bound below the next major, and a
  test enforces both rules. Only `mcp` was bounded; a lockfile-based suite
  stays green while a fresh install resolves a new major, which is how
  `mcp` 2.0 removing `mcp.server.fastmcp` broke fresh installs once already.
  No resolved version changed: the bounds sit above what was already locked.
- A test that fails when any file under `src/` exceeds 1000 lines. The limit
  was a rule with no gate, which is how it drifted past unnoticed.

## v0.40.0 (260816)

### Fixed
- `POST /api/dcat/metadata` writes what it says it saved (260816 review). It
  assigned the catalog metadata and answered `{"status": "saved"}` without the
  `auto_save` every other mutating route calls, so the title, publisher and
  licence a user typed — for exactly the profiles that cannot derive them —
  were gone after a reload.
- An entity type resolved case-insensitively is stored as resolved. Both
  repositories kept the caller's spelling after `require_helper` had resolved
  it, and everything downstream compares canonical names with `==`: a
  lowercase child type was accepted by the resolver and then rejected as an
  invalid child, and a mis-cased PARENT silently broke the reference lookups
  so the child was stored mis-linked rather than refused.
- The spec-builder rule editor no longer destroys a nested predicate through
  its error path. A predicate the rows cannot express is kept via a hidden
  `where_keep`, emitted only by the read-only branch; the error path passed
  empty typed rows unconditionally, flipping the form to the editable branch
  and dropping that flag, so the user's next save wrote `where = None` with no
  message. The same for `when`.
- Parent-scope uniqueness is per parent across files. `validate_directory`
  shares one accumulator so a global-scope rule can span files, but the
  parent-scope key was the file-relative path alone, so `studies[0]` in two
  files was one scope: two MIAPPE investigations each carrying their own OU-1
  and OU-2 reported 2 false "not unique within parent scope" errors, and now
  report none. Records reported invalid become valid; nothing that passed
  starts failing. Single-file validation was never affected. Global scope,
  which no shipped profile declares, is pinned by a test.

### Fixed
- A client built from a supplied spec validates against it (260816 review).
  `MetaseedClient.from_spec()` / `from_yaml()` are the documented way to use a
  custom or generated schema, but `validate()` discarded the spec the client
  held and re-resolved one by (profile, version) from disk — which does not
  exist for a supplied spec, so every entity came back "Unknown entity type:
  X - Profile not found" and a genuinely invalid entity was indistinguishable
  from a valid one. Engine construction is now separable from its loading
  (`build_engine_for_entity`), and `validate_entity` accepts the specs the
  caller already has. Clients built by profile name resolve exactly as before.
- The child-create form no longer offers the parent reference as an editable
  field. Which field that is now comes from the profile's `reference:`
  declaration rather than a guess at `f"{parent.lower()}_id"`, which matched
  only single-word parents with an `_id` suffix: MIAPPE's
  `observation_unit_id` and every ENA `_ref` field were shown to the user, and
  filling one linked the entity to whatever was typed instead of to its parent.

### Changed
- The spec builder names a generated back-reference in snake_case
  (`observation_unit_id`), matching every shipped profile, rather than
  `observationunit_id`. The `reference:` declaration carried the meaning
  either way, so existing generated profiles keep working.

### Fixed
- Exports no longer drop records silently (260816 review).
  - The FAIR Data Station export descends past an entity with no JERM class
    instead of dropping its whole subtree. `walk` returned at the top for an
    unmapped node, so the branch that meant to skip it and keep going never
    ran — an Investigation with an unmapped level beneath it exported nothing
    below that level, and the unmapped-entity warning named only the entity,
    never the content lost under it. Surfaced descendants attach to the
    nearest mapped ancestor.
  - ISA-Tab study tables carry characteristics and factor values authored as
    child entities, not only those embedded in the sample. The MetaboLights
    importer creates them as children, so an import-then-export round trip
    emitted `Characteristics[Organism]` and lost every other qualifier.
  - A factor value is named by `factor_name`, which every ISA-shaped profile
    declares, rather than `category`, which none of them declare on
    `FactorValue`; it had been producing anonymous `Factor Value[]` columns.
    The round-trip fixture that authored the forbidden shape (and so agreed
    with the bug) is corrected.
- An ontology service that cannot be reached reports *not checked*, never
  invalid (260816 review). `TermRouter` caught every source failure and
  returned `None` — the same value that means "asked, and the term is not
  there" — so `check_term` concluded the value was wrong. Measured against the
  shipped examples, an outage where the ontology is known but the term
  endpoint fails reported 61 of 61 ontology values as invalid (miappe/1.1 26,
  miappe/1.2 20, isa/1.0 15); all 61 now report as unchecked, and nothing that
  passed before fails now. The router raises `TermSourceUnavailableError`
  instead of returning `None`, a source that could not be reached no longer
  blocks the other sources from being asked, and `has_ontology_sync` raising
  no longer escapes `check_term` as a crash.
- The `get_ontology_term` MCP tool no longer answers "Term not found" when OLS
  is unreachable: `_make_request` raises on a transport failure or a 5xx and
  returns `None` only for a genuine 4xx, and the tool reports
  `{"checked": false}` with the reason. The same for `list_ontologies`. Three
  of the tool's tests had been passing only because the router swallowed a
  blocked network connection.
- A loaded entity is stored once (260816 review). `load_nested` — the path
  behind `load_yaml` and every shipped example — materialised each embedded
  child as its own node but left the whole child object inside the parent's
  containment field, so every entity below the root was held twice and every
  save or export emitted it twice. The loader now separates an entity's own
  data from the children embedded in it; a plain string in the same field
  names a child rather than embedding one, and is kept as the reference it is.
  This also fixes deletion: `delete_entity` removed the node while the
  parent's copy of the record stayed behind and was re-emitted by `to_dict`
  and by every exporter, which no unlink could have repaired while the
  duplicate existed.
- An unreadable dataset file is no longer written over (260816 review). A
  failed read left `FileEntityRepository` empty and indistinguishable from one
  opened on a new file, so the next create/update/delete serialized that
  emptiness over the user's records — a transient permission error or a
  half-written file destroyed the dataset. A failed load is now recorded and
  every save refuses with `DatasetLoadFailedError`, naming the file and the
  original error, until a `reload()` succeeds; a genuinely empty file still
  saves. Saves are also atomic (write beside the target, rename over it), so
  an interrupted save no longer produces the truncated file that made the
  next load fail.

## v0.39.0 (260815)

### Changed
- `graph.js` is reusable by other applications (#254). The drawing — legend,
  per-type counts, click-to-hide filtering — was closed behind its transport:
  the endpoint was `BASE_URL + '/api/graph'` with no way for a host to name
  its own dataset, and nothing drew the graph on an ordinary page load, so an
  embedder got a blank canvas and no error. `renderGraphData(data)` is now the
  public drawing entry point for a host with its own transport; `loadGraph`
  takes a URL and otherwise reads `window.METASEED_GRAPH_URL` at call time;
  and the graph draws itself on DOMContentLoaded where its container is
  present, suppressible with `METASEED_GRAPH_AUTOLOAD = false`. The contract
  is documented under Guides and gated by a scan test.

## v0.38.0 (260814)

### Removed
- The `api/rest.py` FastAPI app. It was a second REST surface — miappe-only,
  unauthenticated, still titled MIAPPE-API — that nothing served: no CLI
  command, no script entry point, and the hub (the deployed REST surface)
  never mounted it. `from metaseed.api import app` is gone with it.

### Added
- The `isa-miappe-combined` profile ships with the package (#49): the ISA
  framework extended with MIAPPE 1.2 phenotyping entities, reconciled in 0.2
  to one identifier key, one Factor/FactorValue model, geolocation on Study
  and material source inline on BiologicalMaterial (27 entities, 55 rules;
  the naive 0.1 combination is retained). Documented under Profiles.
- Supply-chain closure for releases (#65): Dependabot update PRs (pip and
  actions, weekly, grouped) carry fixes through the same gated CI as any
  change; every release attaches a CycloneDX SBOM of the full locked closure
  (base + all extras + dev); and PEP 740 attestations are explicit on the
  Trusted-Publishing upload. The rest of the acceptance already held: PRs
  are blocked on the lint/format/mypy/pytest gate, coverage publishes on
  release, and pip-audit sweeps the locked closure.
- The DCAT export is SHACL-gated (#29): every suite run validates a sample
  export against the vendored DCAT-AP shapes (SEMICeu/dcat-ap_shacl, pinned
  by vendoring) through pySHACL, offline — with the class declarations the
  shapes' unresolvable owl:imports were meant to supply added explicitly,
  since without them nothing is targeted and every graph "conforms". A
  deliberately broken graph is asserted to report, so a passing report
  means something.
- The hub-consumer contract is a test (#70): `tests/hub_contract.py` freezes
  every symbol metaseed-hub imports from metaseed (generated by
  `scripts/regenerate_hub_contract.py` from the hub's actual imports), and
  the contract test resolves each one — renaming or deleting hub-used
  surface turns metaseed's own CI red before a release ships the break.

### Changed
- `OntologyService` is the synchronous OLS adapter, full stop: its async
  `search`/`get_term` twins — ~200 byte-identical lines that had already
  drifted once and had no production caller — are deleted. Async access goes
  through `TermRouter`, whose `search`/`get_term` wrap the sync
  implementations in a worker thread; a scan test keeps the twins from
  growing back.
- Nested-entity resolution binds to the generated class, not to a mutable
  global. The model context's profile:version was set by every `get_model`
  call and facade build while `_convert_nested_entities` ran at validation
  time — so building a second facade for another profile made every later
  validation through the first resolve nested entities in the WRONG profile
  (MIAPPE and ISA share entity names). A generated class now carries
  `__model_key__` and resolves its nested types under it. The two parallel
  model caches with different key schemes are one: `get_model` reads and
  writes the same `ModelContext` store the resolution reads, and
  `ModelRegistry` is deleted (only `ModelNotFoundError` remains).
- The parent-child invariant of the entity tree is decided in ONE module
  (`facade.linking`, ADR 005): which parent field references a child type,
  the LIST-vs-ENTITY shape rule, and the structural link/unlink. The store
  and both repositories apply the same decisions to their own
  representations, and a gate test fails if the shape rule grows a second
  home — the dangling-reference bug class the 260814 triage fixed three
  times is now unwritable without editing the one module that owns it.

## v0.37.0 (260814)

### Added
- `pride/2.0`: a `Publication` is identified by its `doi` (#249) — `title`
  is a display label two submissions can share. A MAJOR version because the
  marker changes what existing datasets are keyed by; 1.0 is untouched. The
  doi-or-pubmed question is answered with a value-dependent rule
  (`publication_identity`): a publication without a `pubmed_id` must carry a
  `doi`.
- A self-referencing field must not close a loop (#250). Two shapes resolved
  and therefore passed the existence check: a record naming itself, and a
  cycle (`A.parent = B`, `B.parent = A`) — both of which a tree render or an
  ancestry export walks forever. `DatasetValidator` now reports them as
  `reference_self` and `reference_cycle`, blocking value errors on the same
  channel as `reference_integrity`, reported against the cycle's members
  only: a clean record hanging off a pre-existing loop is not blamed for it.

### Fixed
- `to_graph` draws list-valued references — one dashed edge per member — so
  MIAPPE's `Event.observation_unit_ids` finally appears; it is the one link a
  containment tree cannot show (#251). A reference edge whose endpoints
  already share a containment edge carries `redundant: true`: still drawn,
  since the reference is declared, but a consumer can suppress or style it
  without re-deriving containment itself.

## v0.36.0 (260814)

### Fixed
- Silent data-loss and wrong-write paths: `load()` refuses a payload with
  neither `tree` nor `entities` instead of clearing the store; nested-array
  linking no longer depends on input order (a parented mid-level node still
  links its own children); deleting a child removes its identifier from the
  parent's reference field (file and memory paths); an exactly-one-child
  (`type: entity`) reference stays a scalar instead of being coerced into a
  list; nothing the file repository returns can mutate its internal store;
  and a child that fails to save for any reason stays in the form with an
  error instead of vanishing.
- Validation gaps: `validate(cascade=True)` descends entity-typed (singly
  nested) children — Darwin Core's Event and Organism were never visited —
  and no longer feeds the child dict into the parent's model;
  `TypeConverter._to_boolean` reports an unrecognized value as a failed
  conversion instead of storing `False`; a malformed local vocabulary file
  names itself at load and degrades term checks to NOT_CHECKED instead of
  raising inside validators; PRIDE's file-mapping presence rules fire on an
  empty mapping instead of being skipped by it.
- UI correctness: notification toasts show the message, not the literal word
  "error" (seven swapped call sites, now gated by a scan test); every table
  mutation route applies the cell editor's valid-field gate (bulk, paste,
  file parts, malformed paste entries); switching profiles clears the stale
  version; server redirects stay inside the mount prefix; the explore routes
  answer bad input with 400 and name the malformed profile spec; the field
  editor can author `isa_tag`; the typing-time uniqueness warning and the
  conditional formatting in exported workbooks derive from one `key_columns`
  rule.
- MCP and CLI: `create_dataset` proves the profile loads before touching the
  live session; `metaseed migrate` exits non-zero on per-file errors, tracks
  every mutation it makes, and keeps `_node_id` while a dangling parent link
  still needs it; `metaseed validate` reports an unknown entity cleanly and
  runs profile-declared `validate` actions — the ProteomeXchange
  submission/CV checks are now reachable from the shell (new `validate`
  action kind in the adapter registry).
- Profile machinery: a renamed profile (`jerm` → `seek`) resolves on every
  lookup path including the constructor default; `SpecBuilder.update_field`
  validates through the model like `update_rule` (bad `isa_tag`, duplicate
  identifiers, and half-applied edits all refused); the merge comparator
  derives its attribute set from `FieldSpec.model_fields` instead of a
  9-item memory of it; merged entities keep their `seek` role config; the
  least-restrictive merge lets an unconstrained profile drop bounds and
  neither strategy returns an empty `Constraints()`.
- Exports and SEEK: the ISA-Tab investigation names its `s_*.txt` study
  files; a draft value cannot make the ENA XML unparseable; the downloaded
  DCAT card carries the user's catalog metadata and dataset name like the
  page card (exports can now declare host-context parameters); each
  MetaboLights assay reads the MAF it declares (multi-MAF studies import
  again); the SEEK sync resolves JERM roles from ontology annotations at all
  three remaining name-only sites; Controlled Vocabulary ids keep their
  entity namespace end to end; `SyncResult` reports `synced_count` and a
  `created_count` that actually excludes reused records, with reuse recorded
  for studies and assays too.

### Removed
- The `llm` package (`LLMService`): wired to no interface in this repository
  and unused by the hub. Dead per the project rule that a capability
  reachable only as a library call is unfinished work.
- Dead declarations kept alive only by their own tests: `mime_types` on the
  parser protocol and parsers, `get_parent_identifier`,
  `SpecBuilderState.is_active`/`get_entity_names`; the export-side
  `collect_entities_by_type` was renamed `collect_rows_by_type` to end the
  same-name/different-meaning collision; the triplicated spec-builder
  `_require_spec` bodies now delegate to `access.require_spec`, gated.
- Docstrings stopped promising behavior the code does not have: the file
  repository's nested-children format and default-path claims, `create()`'s
  ontology-validation note, the controlled-terms identifier claim, and the
  model registry's version-key contract.

## v0.35.0 (260813)

### Fixed
- `ValidationError.kind` survives every boundary that rebuilds errors: the
  cascade path, `validate_directory`'s file prefixing, the extraction agent's
  `ValidationIssue` (which gained a `kind` field) and the public API's
  `ValidationIssue` (likewise). The VALUE/COMPLETENESS split was computed by
  the validators and then discarded at each of these, so every consumer
  downstream saw a half-entered dataset as blocking-invalid. One gate test per
  boundary now constructs a missing-required-field error and asserts the kind
  arrives.
- Profile versions order numerically. Both "latest version" answers — the
  catalogue's and the spec filesystem's — sorted version strings as text, so
  releasing 1.10 after 1.9 stepped *latest* back to 1.9. One
  `version_sort_key`, used by `SpecLoader.list_versions` (the root every
  caller reads) and the descending list.
- `applies_to` means the same thing at load time and run time. The load-time
  predicate checks matched entity names exact-case and read a bare string as
  "all", while the engine normalises case and separators — the same defect
  class as the 54 silently-disabled rules, one layer up. One matcher
  (`specs.schema.applies_to_entity`), imported by both.
- Six places stopped bypassing the object the application composed for an
  ambient or private one: the facade asks its injected loader for the root
  entity; the adapter-export route builds its client with
  `MetaseedClient.from_facade` instead of `__new__` plus a private attribute;
  `EntityService` takes its change notifier by injection instead of
  try-importing the websocket module; spec notes travel through the
  `SpecPersistence` port instead of a path computed beside its return value;
  the browser CRUD auto-saves pass the app's composed dataset factory; and the
  dataset-manager factory holds one manager per live state (evicted with the
  state) instead of a weakly-held manager that vanished between requests with
  its `current_dataset` silently reset.
- A failing spec-builder edit changes nothing. Rule and field edits assigned
  the stored object attribute by attribute, so an unreadable value halfway
  left the draft half-edited (and the field route 500'd on top). Both build a
  copy and swap it in on success; the rule form's error path now keeps the
  typed `when` rows as well as the `where` rows.
- SEEK provisioning enriches CV terms through the application's term-source
  router instead of a never-passed `OntologyService` parameter: the route now
  supplies the composed source, so a locally configured vocabulary enriches
  too, and a term gets an IRI only when a hit's label matches the enum value
  exactly.

### Removed
- Code superseded by mechanisms that shipped earlier, verified unused by the
  hub before deletion: the `metaseed.core` package (exception hierarchy,
  execution context, serialization helpers — no production callers),
  `validate_term`/`validate_term_sync` (replaced by three-outcome
  `check_term`), `ChainedTermSource` and `VocabularyStore.as_source`
  (replaced by `TermRouter`), `BrAPIClient.observations()` (never called),
  the pre-split 1775-line `ui/static/js/app.js` (its pages load the split
  modules), the unused `ctx` parameters on `SpecLoader` methods, and the
  facade-era `to_json_dict` serialization tests.

### Fixed
- The spawned MCP server can no longer deadlock on its own logging. It was
  started with piped stdout/stderr that nothing drained, so once uvicorn's
  access log filled the ~64KB OS pipe buffer the child's next write blocked
  and the server froze mid-request. Output goes to `mcp-server.log` under the
  user data directory; a server that dies on startup reports the log tail.
- `validate_ontology_terms` (MCP) asks the configured term sources instead of
  speaking OLS4's HTTP API directly, and answers with three outcomes: a
  vocabulary configured on the server is now visible to it, and an OLS outage
  reads as `checked: false`, never as invalid data. The adapter gate has been
  widened to list the tool, and its exemption for this module is now stated to
  cover the OLS catalogue alone — this is the tool that slipped through it.
- The SEEK importer's 4xx degradation fires. It caught `httpx.HTTPStatusError`,
  which `SeekClient` never lets escape (it raises `SeekApiError`), so an
  instance without ISA-JSON observation units aborted the whole import instead
  of importing the study without samples.
- Loading a dataset keeps its catalog metadata. The load set the catalog card
  and then called `reset()`, which clears it — so opening a dataset wiped the
  card it was opening, and the next save persisted the wipe.

## v0.34.0 (260813)

### Added
- A term source declares whether it can serve interactive lookup, and how
  expensive it is to materialise (#247, sections 1 and 4). A picker is a person
  waiting at a keyboard: plan07 measured OLS answering PO in 51 seconds and PATO
  in 32 against 20-55 ms from a local store, which is not slow but unusable —
  while looking fully implemented, because nothing could tell the difference.
  `search_sync(..., interactive=True)` now leaves out a source that says it
  cannot serve a picker, and the term-search route names what it left out as
  `not_asked` so the dialog can say so: a shorter list of results is otherwise
  indistinguishable from there being less to find. Validation still asks
  everything — a slow source is the right thing to ask whether a term exists.
  An adapter that declares nothing is read as interactive, so nothing that works
  today stops working.

  Cost (`none` / `cheap` / `large` / `unknown`) is declared but not acted on
  here: metaseed materialises nothing, so it skips nothing, and the declaration
  exists so a consumer that does import ontologies reads one interface instead
  of inventing its own. `TermRouter.capabilities()` reports the worst case it
  holds.
- `within` constrains validation, not only the picker (#229). A field scoped to
  a branch of an ontology accepted any term in that ontology when a dataset was
  validated, so the restriction held only where values were *offered* — and a
  rule enforced only in the picker is one that typing or importing walks around.
  The term port gained `is_within_sync(term_id, ancestor)`, answered from OLS4's
  `hierarchicalAncestors` endpoint, which is the same relation `childrenOf`
  scopes the picker by.

  Three outcomes, as everywhere else in this check: beneath the branch passes,
  demonstrably outside it is reported (`NOT_IN_BRANCH`), and anything that
  cannot be established is *not checked*. That covers a flat local vocabulary
  with no hierarchy to walk, a service that did not answer, an OLS page that
  truncated, and — the case that matters for MIAPPE — a 200 carrying no
  ancestors, which OLS returns both for a term it does not host and for one
  genuinely at the top of its tree. Reading either as "not beneath" would report
  every Crop Ontology value as wrong.

  `within` is also settable from the field editor. It reached `FieldSpec` and
  the MCP tools when the picker learned about branches, but never the web spec
  builder, so a profile author working there could not declare the restriction
  the validator now enforces.

  Blast radius measured before shipping: two shipped fields declare `within`
  (`Event.event_accession_number` in miappe 1.1 and 1.2) and no shipped example
  populates either, so no shipped data changes verdict. A populated one reports
  *not checked*, since OLS carries no CO_715 and no local vocabulary for it
  ships.
- A reference may declare that its target resolves outside the dataset
  (`reference_scope: external`, spec_version 0.8). A reference has meant one
  thing — the target is a record in this file — but many identifiers are minted
  elsewhere: Darwin Core's `acceptedNameUsageID` names a taxon in GBIF's
  backbone, `occurrenceID` can name a museum catalogue record, and DiSSCo and
  ENA both carry external accessions. Declaring those as plain references
  reported correct data as broken, so they were left undeclared and checked by
  nothing at all. Three outcomes now, as the term check has: a value naming a
  record here is still checked, one that does not is reported as *not checked*,
  and only a within-dataset reference can be broken. "Not checked" is reported
  once per field with a count, not once per value — a checklist of 10,000 rows
  would otherwise repeat itself 10,000 times.
- Darwin Core declares its three self-referencing identifiers (`parentEventID`,
  `acceptedNameUsageID`, `parentNameUsageID`), which had been waiting on that
  key. The cycle guard in `EntityStore` was already in place for them. Measured
  against every shipped example: no error count changed.
- The spreadsheet export leaves an externally-scoped reference column
  unrestricted. Offering only this dataset's rows would tell someone their
  correct value is wrong.
- Validation rules can depend on field values (#211, spec_version 0.7,
  [ADR 003](docs/architecture/decisions/003-value-dependent-validation-rules.md)).
  A `cardinality` rule may carry a `where` predicate selecting which items it
  counts; a `uniqueness` rule may carry one selecting which records it compares,
  which is how an exemption is written; and a `conditional` rule may carry
  `when`/`require`, a requirement that depends on another field's value. The
  legacy `condition` only ever tested whether fields were *present*.
  A rule about *some* of a collection had no expression, so "exactly one
  attribute is the display column" lived in a checker outside metaseed — which
  found a template with zero display columns that metaseed reported as valid.
  A predicate is a mapping (`{field, op, value}`, or a group `all`/`any`/`not`),
  not an expression string: a mapping is canonical under `canonical_json`, so
  reformatting one cannot change a content hash or force a MAJOR bump. Its
  one-line spelling survives as the rendering, which is what messages, the rules
  list and `spec_validate` show.
- A predicated failure states what was counted and out of what — "expected
  exactly 1 of 24 'attributes' to match is_display_column == true, found 0" —
  and names the offending members when there are too many, by the item entity's
  own `is_label`/`is_identifier` field. "Expected 1, got 0" cannot be acted on
  against 24 children.
- Predicates are checked at profile load and by `spec_validate`, not when a
  record is validated: a predicate naming a field the entity does not declare is
  a rule that never fires. Bounds (depth 8, 64 nodes, 256-entry literal lists)
  are structural and checked once, which the form has no backtracking to defeat.
- The rule editor builds a predicate as rows of (field, operator, value), with
  the field offered from the fields the counted entity declares — so the
  load-time "unknown field" error is unreachable from the editor. A predicate
  that nests deeper than rows can show is displayed as its one-line spelling and
  survives a save untouched.
- `SUPPORTED_SPEC_VERSION`: metaseed had no record of which format versions it
  understands, so a profile using a newer construct failed with a message naming
  the rejected key and not the reason. The load error now says which.

### Changed
- `spec_add_rule` and `spec_update_rule` take every attribute of the rule format,
  gated by a test against the model. They took six; an agent could declare a
  cardinality rule's type but not its bounds, a uniqueness rule but not its
  scope.
- A rule edit whose only difference is its predicate is classified on its own
  terms rather than as "the rule changed". Adding a `where` narrows what a rule
  rejects, so it is compatible — except on a rule with `min_items`, where
  narrowing the counted population is exactly how a record that satisfied the
  bound stops satisfying it. Editing or removing one is breaking: predicate
  containment is not decidable here, the same reason a changed `pattern` counts
  as tightened.
- `is_identifier` is compared per entity rather than per field (#212). What a
  consumer can observe is which field an entity is keyed by — the marked one, or
  absent a marker the first non-reference one — so declaring the field inference
  already resolved to is now classified `identifier_declared`, compatible: it
  records a decision the format was already making and re-keys nothing. Marking a
  different field, dropping a marker inference would not reproduce, or reordering
  fields past an undeclared identifier is `identifier_changed`, breaking. Before
  this, saying out loud what a profile already did counted as a breaking change,
  which is why three shipped profiles carried an undeclared identifier.
- `isa` 1.0 `Process`, `miappe-htp` 1.0 `Location` and `ObservationLevelHierarchy`
  declare the identifier they were already keyed by. No version was bumped,
  because nothing about them is keyed differently. Two of the five entities the
  advisory reported are unchanged and stay reported: `miappe-htp`
  `SpatialDistribution` is a value object with no identity of its own, and
  `pride` `Publication` is identified by its `doi` rather than the `title`
  inference picks — moving it is a real change and belongs in a MAJOR version.
- One definition of the identifier rule, `specs.schema.identifying_field`, used by
  the facade, the weak-identifier advisory and the comparator. It was written out
  three times; three copies of an inference rule is three chances to disagree
  about what a dataset is keyed by.

### Fixed
- A validation rule scoped to a nested entity now fires on the path the
  application validates through. A profile writes `SampleAttribute`, the dataset
  validator reaches a nested child as `sample_attribute` and its own root as
  `sampletype`, and the three were compared on case alone — so the root matched
  and every nested entity missed, silently disabling 54 rules across the shipped
  profiles. Found while wiring #211, whose first constraint is a rule on a
  nested entity. Blast radius measured against every shipped example: no error
  count changed.
- An entity annotated with the JERM class it represents is exported as it
  (#234). The SEEK role map read the entity's *name* against nine strings and
  never its `ontology_term`, so a profile derived faithfully from JERM exported
  almost nothing: an entity called `Experiment` annotated as an Assay was
  skipped, while one merely named `Assay` and annotated with nothing was
  exported. The annotations were decorative on this path.

  Only the class an annotation *names* is read — `JERM:Assay`,
  `…JERMOntology#Assay`. The recognised names were read from the ontology
  itself: JERM declares 294 classes and no numeric accession at all, so
  `JERM:00021` names nothing there and stays unmapped rather than being matched
  against an invented table. Four of those classes have a place in the chain
  SEEK's reader walks, along with the three subclasses JERM declares beneath
  `Assay`; the observation-unit level is PPEO's `observation_unit`, which is
  what this exporter emits. `treatment` is a real JERM class with no slot in
  that chain, so it is reported rather than placed as something it is not. A
  release-gated test re-reads the ontology and fails when a recognised name is
  not in it.
- An entity that maps to no JERM class is named in a warning rather than
  silently omitted. The complaint in #234 was not that the export fails, but
  that it succeeds while producing less than its author expects.
- miappe 1.2 types its method and event accessions as ontology terms, as 1.1
  and the MIAPPE checklist do; they were plain strings, so their values were
  checked by nothing. The event field also carries the branch the standard
  names (`within: CO_715:0000006`). Both stay optional and sit beside required
  free-text names — MIAPPE's own answer to a method or event with no term yet
  is to fill in the name and leave the accession empty, and an `ontology_term`
  field accepts free text and omission regardless. The 1.2 example carried the
  same wrong AGRO accessions as 1.1 (`AGRO:00000007` is *desuckering*,
  `AGRO:00000006` is *irrigation process*); removed on the same grounds. Both
  MIAPPE examples now validate clean.
- A child entity held singly is validated as an entity. Only list-valued
  children were descended into, so an entity nested one-to-one — Darwin Core
  nests both its Event and its Organism this way — was never visited: its own
  fields were checked against its *parent's* spec, reporting every one of them
  as "Extra inputs are not permitted", and its references were never checked at
  all.
- Reference integrity works for a profile that does not use MIAPPE's
  `unique_id`. Only entities carrying a field literally named `unique_id` were
  ever registered, so for Darwin Core (`occurrenceID`), DiSSCo (`identifier`)
  and ENA (`alias`) the registry stayed empty and a declared reference could
  never resolve. Nothing reported it, because a reference is only checked when
  the field holds a value — the failure was invisible until Darwin Core
  declared its first reference and a plainly-present identifier came back "not
  found". The referenced field is now read from the declaration itself: a field
  saying `reference: "Occurrence.occurrenceID"` states that an Occurrence is
  referenced by its `occurrenceID`. `unique_id` is still always registered.
- Darwin Core declares its within-dataset cross-references, as the other five
  profiles do: `Event.occurrenceID`, `Location.eventID`,
  `Identification.occurrenceID` and `Organism.occurrenceID` (#246). A consumer
  rendering reference pickers gave DwC users free-text boxes where every other
  profile got a checked lookup. Measured across every shipped example: no new
  errors in Darwin Core, and one surfaced in the ISA example — `assay_id`
  declares `reference: "Assay.filename"` and names something that is not an
  Assay filename, which the empty registry had been hiding.
- A reference field naming its own entity type can build a hierarchy without
  the risk of closing one. Because a reference decides the parent here, two
  records naming each other each became the other's parent: the dataset then
  had no roots at all — every node had a parent, so it read as empty — and the
  `children` graph recursed without end. A node is never parented under one of
  its own descendants, and the refusal is logged rather than silent.

  No shipped profile declares a self-referencing reference yet, so nothing
  changes today. Darwin Core is full of them — `parentEventID` names another
  Event, `acceptedNameUsageID` another Taxon — and this is what has to be right
  before those can be declared (#246).

### Changed
- An `ontology_term` field that names no ontologies means **any** ontology, now
  stated in the schema and pinned by tests rather than left to be inferred
  (#246). The value is still checked to be a real term; only the restriction is
  lifted. `isa` and `seek` both declare `OntologyAnnotation.term_accession`
  this way, so the one field whose declared type is literally "ontology term"
  offered a consumer nothing — read as "no lookup" instead of "unrestricted".
  A test also fails if no shipped profile relies on this any more, so the
  documented meaning cannot come to rest on nothing.

## v0.33.0 (260812)

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
- MIAPPE's own specification decides what its accession fields take, replacing
  declarations that contradicted it (#248). The checklist says a scale
  accession comes from the **Crop Ontology** (illustrated with
  `CO_322:0000510`); the profiles declared the Units Ontology, which made every
  Crop Ontology scale in the shipped example report as wrong — the declaration
  was at fault, not the data. Method accessions now allow the Trait Ontology,
  as the standard states. The event accession keeps `co_715` and gains
  `within: CO_715:0000006`, because the standard scopes it to that branch.

  The example's event accessions are removed rather than replaced: they named
  real AGRO terms meaning the wrong things — `AGRO:00000007` is *desuckering*,
  not sowing; `AGRO:00000006` is *irrigation process*, not fertilization — and
  `AGRO:00000012` does not exist at all. MIAPPE requires a CO_715 term, CO_715
  is not in OLS and AgroPortal needs a key, so no real accession could be
  verified. An absent optional field is honest; a wrong one teaches a wrong
  identifier. The ISA example's five unresolvable EFO and NCBITaxon accessions
  and miappe 1.2's Units Ontology scales were removed on the same grounds.
- Validating a dataset no longer crashes when a reference field holds several
  identifiers or an embedded child. Both went straight into a set lookup, so
  three of the seven shipped examples — isa 1.0, miappe 1.1 and miappe 1.2 —
  aborted with `TypeError: unhashable type`, and no dataset shaped like them
  could be validated at all. An embedded object is not a dangling reference:
  the entity is present and is checked when the walk reaches it.
- A reference dropdown offers each row once. Every entity is present twice —
  as a stored node, and as the dict still embedded in its parent — and the
  picker walked both, so it listed 96 Samples for a dataset holding 24 and
  doubled every other type. The export was fixed for this; the picker was left
  behind. Measured against the MIAPPE example: option counts now equal the
  stored entities exactly, type by type, so nothing was dropped along with the
  repeats.
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
- Reading a document is its own module (`metaseed.facade.documents`) rather
  than four methods on a facade that had grown to thirty-eight. It depends on
  three questions — store this entity, what may nest in this type, does the
  profile declare containment — stated as a protocol, so it can be exercised
  without a profile, a spec loader or a store. `ProfileFacade.load_nested` and
  `load_yaml` are unchanged for callers.
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
