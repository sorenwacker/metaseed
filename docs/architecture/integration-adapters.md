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
| PRIDE | `pride` profile | `submission.px` |
| MetaboLights | `metabolights` profile | ISA-Tab + MAF |

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
- **Schema-valid output where it counts.** The ENA exporter's study/sample/run
  XML **validate against ENA's official SRA XSDs** — i.e. the output is not just
  well-formed, it would be accepted.

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

The eight adapters are a real first step, **not production-validated.** Each was
smoke-tested against a single live record (which already caught real bugs), and
the clients now page and retry. Still open: broader accession coverage, export
validation for BrAPI/PRIDE/MetaboLights (ENA is XSD-valid), and verification that
exports are accepted by the live submission systems. Tracking: umbrella #75,
importers epic #76.
