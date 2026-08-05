# Publishing to FAIRDOM-SEEK

Metaseed can set up a [FAIRDOM-SEEK](https://seek4science.org/) instance from a
profile and push a dataset into it, over SEEK's API. This guide is the
task-oriented walkthrough; for the RDF format and the Python entry points see
[SEEK Export](../architecture/seek-export.md).

## What the export produces

A profile and a dataset map onto SEEK in two separate ways, because SEEK treats
them differently:

| From your profile / dataset | Becomes in SEEK | How |
|-----------------------------|-----------------|-----|
| Entities that map to a JERM `Sample` (by SEEK role, or by name) | **Sample Types** and their **Controlled Vocabularies** | API — the *Provision* button |
| The entities of a loaded dataset | **Investigations, Studies, Assays, Samples** | API — the *Sync* button |
| Fields on Investigation / Study / Assay | **Extended Metadata** | Manual — a file a SEEK admin uploads |

The split is SEEK's, not metaseed's: SEEK only lets an administrator create
Extended Metadata Types, and not over its API, so that part cannot be
self-service.

## One-time setup

The SEEK page is hidden until the adapter is enabled and pointed at an instance.

1. Install the extra: `pip install 'metaseed[seek]'` (it needs `httpx`; the page
   says so if it is missing).
2. Open **Settings → Plugins**, enable **SEEK**, and set:
   - **URL** — your SEEK instance, e.g. `http://localhost:3000` (required).
   - **API key** — a SEEK personal access token (optional, but *Provision* and
     *Sync* are disabled without it, since both write to SEEK).

## The workflow

Open the **FAIRDOM-SEEK** page (`/seek`). It has two numbered steps and a
file-export fallback.

### 1 · Configure the model in SEEK

Choose the profile and click **Provision model →**. This creates its Controlled
Vocabularies and Sample Types in the selected **Project** — a project *on your
SEEK server*, which every SEEK resource must belong to. Re-running is safe: it
reuses what already exists rather than duplicating it.

This step needs no loaded dataset — it describes a *profile*, so you can
provision before you have built anything.

#### Browse what will be created first

Below the profile chooser, **What this will create in SEEK** shows the model the
selected profile and version project onto, before anything is written:

- **Sample Types** — each entity that becomes a SEEK Sample Type, expandable to
  its columns (name, type, and whether it is a controlled vocabulary). This is
  read from the same plan *Provision* executes, so it cannot drift from what is
  created.
- **Extended Metadata** — the custom fields the Investigation, Study and Assay
  records carry. SEEK's own record fields (identifier, title, description) and
  the nested structure are not listed, because they are not Extended Metadata.

The panel refreshes when you change the profile or version, and never writes to
SEEK — it is there to check a profile maps the way you expect before you
provision or sync.

### 2 · Sync the dataset to SEEK

With a dataset loaded, click **Sync to SEEK →**. It pushes the dataset's
entities in as Investigations, Studies, Assays and Samples, matched to the
Sample Types provisioned in step 1.

If this reports *no dataset loaded*, that is why: unlike *Provision*, *Sync*
acts on the dataset you have open. Load or create one first.

### Or export a file

**Download SEEK ISA RDF (.ttl) →** gives you the dataset as a Turtle file to
import through SEEK's own tool, instead of the API. Useful when you cannot give
metaseed an API key, or want to review the file first.

To import it, in SEEK:

1. Open a **Project → Import from FAIR Data Station**.
2. Upload the `.ttl` on the **FAIR DS TTL** tab. (It is a tab, easy to miss; the
   JSON tab is selected by default and disables the file field.)
3. SEEK previews what it found. Press **Submit**.
4. The import runs as a background job — the status panel moves from *Queued* to
   *Completed*.

## Notes and limits

- **Provision needs no dataset; Sync does.** They act on different things — a
  profile and a loaded dataset respectively.
- **"Project" is a project on your SEEK instance**, fetched live from it, not a
  metaseed concept.
- **Extended Metadata is derived from a dataset's *non-core* annotations.** An
  Investigation carrying only title, identifier and description yields no
  Extended Metadata Type — that is SEEK reading the file correctly, not an
  export failure. The Extended Metadata download exists for the fields that go
  beyond SEEK's core set.
- SEEK reads the ISA hierarchy **positionally**. A profile whose entities do not
  sit at the expected Investigation → Study → (ObservationUnit →) Sample → Assay
  depth will import at a shifted level. An entity's **SEEK role** (set on the
  entity in the Spec Builder) re-types the exported node — choosing which JERM
  class it becomes — but does not move it in the tree, which SEEK infers from
  where the entity sits.
