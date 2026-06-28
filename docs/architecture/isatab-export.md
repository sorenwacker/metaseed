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

## MetaboLights export

```python
from metaseed.metabolights import to_metabolights

docs = to_metabolights(client)   # ISA-Tab + one m_*.txt MAF per assay
```

`to_metabolights` is `to_isatab` plus the MetaboLights-specific **MAF**
(Metabolite Assignment File) — a `m_*.txt` skeleton carrying the standard MAF
column header for each assay. So `import_accession` and `to_metabolights`
round-trip through the `metabolights` profile.
