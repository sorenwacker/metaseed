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
3. Click **Check connection**. metaseed asks the instance for the projects the
   key can see and reports one of: connected with the number of visible
   projects; the host cannot be resolved; nothing answered at the host; the key
   was rejected (HTTP 401/403); the instance is down (HTTP 5xx); or the URL is
   not a SEEK API root (HTTP 404). Each message names the cause, so a wrong
   hostname is not reported as a bad key. The check reads only; it writes
   nothing to SEEK.
4. Pick the **Project** from the list the check returned and save it. Every
   SEEK resource metaseed creates belongs to this project. The SEEK page
   preselects it; you can still override it there for a single action.

## The workflow

Open the **FAIRDOM-SEEK** page (`/seek`). It has two numbered steps and a
file-export fallback.

### 1 · Configure the model in SEEK

Choose the profile and click **Provision model →**. This creates its Controlled
Vocabularies and Sample Types in the selected **Project** — a project *on your
SEEK server*, which every SEEK resource must belong to. The project saved on the
Plugins page is preselected. If the project list is empty, the page shows the
same diagnosis as **Check connection** on the Plugins page. Re-running is safe: it
reuses what already exists rather than duplicating it.

This step needs no loaded dataset — it describes a *profile*, so you can
provision before you have built anything. The page keeps the profile and
version you chose after the action, so the preview and the Extended Metadata
download below it refer to what you just provisioned, not to the loaded
dataset's profile.

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

#### Install the ISA Templates (one admin step per profile)

SEEK's ISA-JSON exporter reads each Sample Type's ISA **Template**, and
Templates can only be installed by a SEEK administrator — not over the API. The
page's **Download ISA Templates (.json) →** button produces the file for the
selected profile and version; a SEEK admin uploads it under **Templates →
Populate Templates**, where it runs as a background job. Re-uploading is safe:
existing Templates are kept.

Without this step, *Sync* refuses with an error naming the missing Template
(e.g. `no ISA Template titled '<profile> study source'`). One upload per
profile and version is enough; every later sync reuses the installed Templates.

### 2 · Sync the dataset to SEEK

With a dataset loaded, click **Sync to SEEK →**. It pushes the dataset's
entities in as Investigations, Studies, Assays and Samples, matched to the
Sample Types provisioned in step 1.

If this reports *no dataset loaded*, that is why: unlike *Provision*, *Sync*
acts on the dataset you have open. Load or create one first.

A Sample that nothing links into the ISA tree — one whose material chain never
reaches an Assay, in a dataset with no Assay at all — is still created, but
reported as *unlinked*: SEEK finds a Sample from its Investigation only through
an Assay, so an unlinked record is reachable solely by listing the project's
samples, and a re-import drops it.

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
- **SEEK derives Extended Metadata Types from instances, not from property
  definitions.** Its *Extended Metadata Types → create from FAIR Data Station
  TTL* flow walks the `jerm:Investigation`, `jerm:Study` and `jerm:Assay` nodes
  in the file and builds one type per level from the annotations those nodes
  carry; a file holding only `rdf:Property` definitions yields "no new Extended
  Metadata Types". The **Download Extended Metadata (.ttl)** file therefore
  contains one skeleton instance per ISA level (Investigation → Study → Assay,
  linked by `jerm:hasPart`) carrying every *non-core* field of the entity that
  fills that role, with a placeholder value, plus the property definitions.
  A level whose entity has only title, identifier and description (MIAPPE's
  Investigation, for example) still appears in the file but produces no type,
  because there is nothing beyond SEEK's core set to add.
- SEEK reads the ISA hierarchy **positionally**. A profile whose entities do not
  sit at the expected Investigation → Study → (ObservationUnit →) Sample → Assay
  depth will import at a shifted level. An entity's **SEEK role** (set on the
  entity in the Spec Builder) re-types the exported node — choosing which JERM
  class it becomes — but does not move it in the tree, which SEEK infers from
  where the entity sits.

## What an entity is exported as

Three things are consulted, in order: the entity's **SEEK role**, then the class
its own `ontology_term` names, then its type name. An entity annotated with the
class it represents therefore exports as that class whatever it is called, which
is what a profile derived from JERM needs.

The class names recognised in an annotation are those the export can place:

| Annotation names | Exported as |
|---|---|
| `Investigation`, `Study`, `Sample` | itself |
| `Assay`, and JERM's `experimental_assay`, `informatics_analysis`, `modelling_analysis` | Assay |
| PPEO's `observation_unit` | ObservationUnit |

Anything else is left out, and every entity left out is named in a warning when
the export runs. That includes real JERM classes with no position in the chain
SEEK reads — `treatment`, `Data`, `Model`, `SOP` — which are reported rather
than placed as something they are not. JERM identifies its classes by name and
has no numeric accessions, so an annotation such as `JERM:00021` names nothing
in it; give such an entity a SEEK role instead.
