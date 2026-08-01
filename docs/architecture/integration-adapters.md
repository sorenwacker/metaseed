# Integration Adapters: Approach and Decisions

metaseed is a two-way bridge to scientific data repositories: **importers** pull
public metadata into a validated profile dataset, and **exporters** render a
dataset back into a repository's submission format. This page records the
approach, what worked, what didn't, and why these choices were made — so the
next adapter (and the next contributor) starts from the rationale, not a blank
page.

## The shape

Every adapter follows one seam, in one of two directions:

- **Import:** `accession/server → fetch metadata → map (spec-driven) → validate → dataset`
- **Export:** `dataset → render → submission documents`

Each repository lives in its own package (`metaseed.<repo>`) with at most three
parts: a `client` (network I/O), a `mapper` (pure import logic), and an `export`
(pure render logic). ENA, BrAPI, PRIDE, and MetaboLights all implement this; ENA
was built first as the reference and the rest mirror it.

| Repo | Import target | Export format |
|------|---------------|---------------|
| ENA | `ena` profile | SRA submission XML |
| BrAPI | `miappe` profile | BrAPI v2 JSON |
| PRIDE | `pride` profile | `submission.px` + SDRF |
| MetaboLights | `metabolights` profile | ISA-Tab + MAF |

## The action registry

`metaseed.adapters` is the single declarative list of what each adapter offers.
An `Action` names a `kind` (`import`, `export`, `push`), a lazy
`"module:function"` `ref`, and a `surface` telling a host where to group its
control. `actions_for_profile(profile, kind=..., surface=...)` is the only call a
host needs: a new adapter capability appears in the web UI and in the hub by
declaring itself here, never by editing a host.

| Action | Kind | Profile | Takes |
|--------|------|---------|-------|
| `ena-import` | import | `ena` | ENA accession |
| `pride-import` | import | `pride` | ProteomeXchange accession |
| `metabolights-import` | import | `metabolights` | MetaboLights study accession |
| `brapi-import` | import | `miappe` | BrAPI v2 server URL |
| `ena` | export | `ena` | — |
| `pride` | export | `pride` | — |
| `metabolights` | export | `metabolights` | — |

Every import action takes exactly one string, so a host renders one text input
and calls `action.resolve()(value)`. What that string *means* differs — an
accession for the three archives, a server URL for BrAPI — so each action
carries an `input_label` and `input_placeholder` for the prompt. Without them a
host would have to hard-code per-adapter wording, which is the coupling the
registry exists to remove.

## Running an import

Resolving the action is only half of an import: the returned `MetaseedClient`
has to replace what the host is editing. `metaseed.ui.datasets.import_from_source`
does both — it looks the action up with `adapters.import_action_for_profile`,
calls it, installs the resulting facade on the `AppState`, and returns the
imported profile, version and root count. Every host in this repository goes
through it, so an importer cannot behave differently depending on where it was
started from.

Two failures are distinguished, because the fix differs:

- `NoImporterError` — the profile declares no import action. The message lists
  the profiles that do.
- `EmptyImportError` — the importer ran and returned nothing. The accession is
  wrong or has no public metadata; the dataset is left untouched.

`ModuleNotFoundError` is left to propagate: it means the adapter's extra
(`metaseed[pride]`) is not installed, which no host can resolve on the user's
behalf.

### The hosts

| Host | Entry point |
|------|-------------|
| Web UI | `POST /import/source` with `key` and `value` form fields; the control is rendered on the dataset page from `import_options_for_profile` |
| MCP | the `import_from_database` tool (`profile`, `accession`, `name`) |
| Library | `metaseed.<repo>.import_accession(...)` directly |

The web UI renders one import control per action the active profile offers, next
to the adapter exports, and saves nothing until the import succeeds. The MCP
tool additionally saves the result under a dataset name, because an agent has no
page to leave the result sitting on.

## Decisions (and why)

- **Optional extras, not core deps.** Each adapter installs with
  `metaseed[<repo>]` (its network/parse deps), so core stays lean and
  single-user-foundation-focused. Importing `metaseed.<repo>` pulls in **no web
  stack** — a guard test enforces this. Consumers take only what they need.
- **Spec-driven mapping.** The existing profiles *are* the contract; adapters map
  to/from profile entities rather than inventing a parallel schema. The
  `metaseed.isatab` writer is shared by the `metabolights` and `isa` profiles
  (and is the head start for FAIRDOM-SEEK) because ISA-Tab is their common
  backbone.
- **Reference-adapter-first.** Build one vertical (ENA) end to end, prove the
  seam, then replicate. This made the other three cheap — built largely by
  parallel agents copying the ENA files.
- **Metadata, not data.** Adapters reference raw files (FASTQ, RAW/mzML, spectra)
  by URL/name; they never download them. "Import all of an accession" means all
  of its *metadata*.
- **Pure mappers/writers + injectable clients.** The mapper and exporter take
  plain dicts / a `MetaseedClient` and touch no network, so they are unit-tested
  from fixtures. The client accepts an injected `httpx.Client`, so request
  shaping is tested with a mock transport. The network call itself is one
  `@network`-marked smoke test.
- **Lenient build.** Entities are created with `skip_validation` during import,
  so a record missing a field never aborts the import; `client.validate()`
  reports gaps afterward.

## What worked

- **The seam replicated cleanly.** Six parallel subagents (in isolated git
  worktrees) built 7 of the 8 adapters by mirroring the ENA reference; each was
  then reviewed and live-tested by hand.
- **Shared helpers removed duplication.** `metaseed._http.request_json`
  (retry/backoff) and `metaseed.isatab.to_isatab` are written once and reused by
  all the relevant adapters.
- **Every exporter has a conformance test.** The ENA export **validates against
  ENA's official SRA XSDs** (external schema — the gold standard); the PRIDE,
  MetaboLights, and BrAPI exports have structural/shape conformance tests
  (required px `MTD`/`FMH`/`FME` lines, the ISA-Tab sections + study/assay/MAF
  files, and the BrAPI v2 object shape via jsonschema). All are `@network`
  round-trips against a real record.
- **Importers tested across diverse accessions.** Each importer was run against
  several real, varied accessions (ENA run/sample/study incl. a 495-file study;
  four PXD projects incl. a 2384-file one; four MTBLS studies) without surfacing
  new mapping gaps.

## What didn't work (and the lessons)

- **Hermetic tests passed against wrong assumptions.** Agents wrote fixtures
  encoding *guessed* API shapes; the hermetic tests then passed trivially.
  Live data exposed the gaps:
  - MetaboLights records people/publications on the **study**, not the
    investigation — the importer read the (empty) investigation level and
    silently dropped every study's contributors. Caught only by importing real
    `MTBLS1`. Fixed; the fixture now matches the real API and guards it.
  - The PRIDE dataset is a single **composed** `Dataset` with nested lists, not
    flat ref-linked entities — inspecting the flat entity list looked empty until
    we read the nested fields.
  - **Lesson:** a live smoke test per adapter is non-negotiable; fixtures must be
    derived from real responses, not invented.
- **Pagination was silently dropped.** The first cut of the PRIDE and BrAPI
  clients fetched a single page, truncating large datasets (PXD000561: 100 of
  2384 files). Only visible by testing a *large* accession. Both now page
  through; tests guard it.
- **A subagent hit a session limit mid-task.** The ISA-Tab exporter agent stopped
  after writing the writer; the work was salvaged and finished by hand.
- **The commit hook can silently abort.** `ruff format` running in pre-commit can
  reformat a staged file and abort the commit while a script's echo claims
  success — always verify `git log` and pre-format before committing.

## Honest status

The eight adapters now page and retry, each importer has been exercised across
several diverse live accessions, and every exporter has a conformance test
(ENA against the official XSD; the rest structural/shape). The one remaining
unknown is **acceptance by the live submission systems** — no export has yet
been round-tripped through a real ENA/PRIDE/MetaboLights/BrAPI submission
endpoint. Tracking: umbrella #75, importers epic #76.
