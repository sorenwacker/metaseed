# MIAPPE-HTP v1.0

The `miappe-htp` profile is a high-throughput-phenotyping variant of MIAPPE. It
keeps the MIAPPE investigation/study backbone but expands the model to 28
entities that capture observation levels, spatial layout, growth facilities and
the trait/method/scale decomposition of observed variables. Most entities are
keyed by `name` (a few — `Observation`, `FactorValue`, `ExperimentalDesign`,
`SpatialDistribution` — use other identifying fields). The root entity is
**`Investigation`**.

`SpatialDistribution` has no identifier of its own. It is a value object — a
description and three coordinates — nested one-to-one in the ObservationUnit it
describes, and its identity is that position rather than any of its fields. The
spec-builder advisory reports it for that reason and the report is accurate; no
field is marked, because marking one would state an identity the entity does not
have.

## Entities

| Category | Entities |
|----------|----------|
| **Backbone** | Investigation, Study |
| **Material** | BiologicalMaterial, MaterialSource, Sample |
| **Observation** | ObservationUnit, ObservationLevel, ObservationLevelHierarchy, Observation, ObservedVariable, Trait, Method, Scale |
| **Design** | ExperimentalDesign, Factor, FactorValue |
| **Environment** | Environment, EnvironmentParameter, GrowthFacility, Event |
| **Layout** | Location, Country, SpatialDistribution, SpatialDistributionType |
| **People** | Person, Role, Institution |
| **Data** | DataFile |

## Entity-Relationship Diagram

```mermaid
erDiagram
    Investigation {
        string name
    }
    Study {
        string name
    }
    ObservationUnit {
        string name
    }
    Sample {
        string name
    }
    Observation {
        string value
        string timestamp
    }
    ObservedVariable {
        string name
    }
    Trait {
        string name
    }
    Method {
        string name
    }
    Scale {
        string name
    }

    Investigation ||--o{ Study : studies
    ObservationUnit }o--|| Study : study
    Sample }o--|| ObservationUnit : observation_unit
    ObservationUnit ||--o{ Observation : observations
    Observation }o--|| ObservedVariable : variable
    ObservedVariable }o--|| Trait : trait
    ObservedVariable }o--|| Method : method
    ObservedVariable }o--|| Scale : scale
```

## Usage

```python
from metaseed import miappe_htp

h = miappe_htp()

investigation = h.Investigation(name="Wheat high-throughput phenotyping investigation")
```

## References

| Resource | URL |
|----------|-----|
| MIAPPE | <https://www.miappe.org/> |
