# ISA and MIAPPE Comparison

Two metadata standards for life science experiments. See [Diagrams](diagrams.md) for visual comparison.

## When to Use Each

| Use Case | Profile |
|----------|---------|
| Multi-omics (genomics, proteomics, metabolomics) | `isa` |
| Plant phenotyping, field trials | `miappe` |
| Both multi-omics and phenotyping | `isa-miappe-combined` |

## Key Differences

| Aspect | ISA | MIAPPE |
|--------|-----|--------|
| Focus | Assay workflows, data provenance | Field trials, germplasm, environment |
| Model | Process-centric (DAG of transformations) | Observation-centric (plots with measurements) |
| Person | `first_name` + `last_name` | `name` |
| Publication | Structured entity | URL list |

## Entity Mapping

### Shared Core

Investigation, Study, Person, Sample, Factor, FactorValue, DataFile

### ISA-Specific

Assay, Protocol, Source, Extract, LabeledExtract, Process, OntologyAnnotation, Characteristic

### MIAPPE-Specific

BiologicalMaterial, ObservationUnit, ObservedVariable, Event, Environment, Location, MaterialSource

## Combined Profile (isa-miappe-combined)

Unified model with both ISA and MIAPPE entities.

| Version | Changes |
|---------|---------|
| **v1.0** | Initial unified model |
| **v2.0** | New Experiment entity, reference-based ownership, unified Person naming |

**v2.0 Ownership Model:**

- **Study owns**: BiologicalMaterials, ObservationUnits, Samples, Protocols (shared pool)
- **Experiment owns**: Events, Environments, Assays (time/location specific)
- **Experiment references**: `observation_unit_ids`, `sample_ids` from Study

```python
from metaseed.facade import ProfileFacade

combined = ProfileFacade("isa-miappe-combined", "2.0")

# Both ISA and MIAPPE entities available
protocol = combined.Protocol(name="RNA Extraction")
material = combined.BiologicalMaterial(identifier="BM-001", organism="Zea mays")
```

## References

- [ISA Tools](https://isa-tools.org/)
- [MIAPPE](https://www.miappe.org/)
- [MIAPPE 1.1 Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7317793/)
- [PPEO Ontology](https://agroportal.lirmm.fr/ontologies/PPEO)
