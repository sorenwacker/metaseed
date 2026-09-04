# ISA-Tab Export

A shared, reusable ISA-Tab writer plus the MetaboLights submission exporter that
wraps it — the export side of the integration bridge.

## Shared ISA-Tab writer

```python
from metaseed.isatab import to_isatab

docs = to_isatab(client)   # {"i_Investigation.txt": ..., "s_<study>.txt": ..., "a_<assay>.txt": ...}
```

`to_isatab` renders any **ISA-shaped** metaseed dataset (Investigation → Study →
{Person, Publication, Factor, Protocol, Assay}) as ISA-Tab documents: the
labeled-section `i_Investigation.txt`, plus a study file and assay file per study
and assay. Pure and dependency-free (stdlib tab-delimited text); files are
referenced, never read or written.

Because ISA-Tab is the shared backbone of the `isa` and `metabolights` profiles
(and FAIRDOM-SEEK, #33), this one writer serves all of them.

### Every label a section defines is written

ISA-Tab states that each investigation-file section "MUST contain the following
labels", and the reference investigation file published with the specification
writes them all — many with empty values. The writer does the same: a label the
profile has no field for is emitted with an empty value rather than left out,
because a consumer reads the file by its labels and cannot tell an absent label
from an absent value.

### Ontology annotations travel as a triplet

An ontology term is three rows in the investigation file — the term, its
`Term Accession Number`, then its `Term Source REF` — and three columns in a
study or assay table, where the order is the other way round (`Term Source REF`
before `Term Accession Number`). Both are written wherever a term appears.

No ISA-shaped profile stores the ontology as its own field, so the source is
read back from the accession: `PATO:0000461` and the OBO PURL
`http://purl.obolibrary.org/obo/OBI_0500020` each name their ontology in the
identifier. Those names are what the `ONTOLOGY SOURCE REFERENCE` section
declares, so a `Term Source REF` used elsewhere resolves to a declared source.

### A protocol's parameters and the process that links materials

`Study Protocol Parameters Name` carries each protocol's `ProtocolParameter`
entities, semicolon-separated in that protocol's column — they are separate
entities in the profile, and omitting the row dropped the only record of what a
protocol was run with.

In a study table, a `Protocol REF` column sits between `Source Name` and
`Sample Name`: ISA-Tab links the two materials through a process, and the
protocol it names MUST be of type `sample collection`. The writer picks the
study's protocol of that type, and leaves the cell empty when the study declares
none rather than referencing a protocol of the wrong type.

## MetaboLights export

```python
from metaseed.metabolights import to_metabolights

docs = to_metabolights(client)   # ISA-Tab + one m_*.txt MAF per assay
```

`to_metabolights` is `to_isatab` plus the MetaboLights-specific **MAF**
(Metabolite Assignment File) — a `m_*.txt` skeleton carrying the standard MAF
column header for each assay. So `import_accession` and `to_metabolights`
round-trip through the `metabolights` profile.
