# MIAPPE v1.1

14 entities for plant phenotyping experiments.

```mermaid
flowchart TB
    subgraph core["Core"]
        INV[Investigation]
        STU[Study]
        PER[Person]
    end

    subgraph material["Plant Material"]
        BM[BiologicalMaterial]
        MS[MaterialSource]
    end

    subgraph observation["Observations"]
        OU[ObservationUnit]
        OV[ObservedVariable]
        SAM[Sample]
    end

    subgraph experiment["Experiment Context"]
        FAC[Factor]
        FV[FactorValue]
        EVT[Event]
        ENV[Environment]
        LOC[Location]
    end

    subgraph output["Output"]
        DF[DataFile]
    end

    INV --> STU
    INV --> PER
    STU --> BM
    STU --> OU
    STU --> OV
    STU --> FAC
    STU --> EVT
    STU --> ENV
    STU -.-> LOC
    BM --> MS
    OU --> SAM
    FAC --> FV
    STU --> DF

    classDef core fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef material fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef obs fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef exp fill:#fce4ec,stroke:#e91e63,stroke-width:2px
    classDef out fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px

    class INV,STU,PER core
    class BM,MS material
    class OU,OV,SAM obs
    class FAC,FV,EVT,ENV,LOC exp
    class DF out
```

## Entities

| Category | Entities |
|----------|----------|
| **Core** | Investigation, Study, Person |
| **Plant Material** | BiologicalMaterial, MaterialSource |
| **Observations** | ObservationUnit, ObservedVariable, Sample |
| **Experiment Context** | Factor, FactorValue, Event, Environment, Location |
| **Output** | DataFile |

## Key Concepts

- **Observation-centric**: Experiments modeled as observation units with measurements
- **Field trial-oriented**: Plots, blocks, replicates
- **Trait-centric**: Measurements defined by trait/method/scale (ObservedVariable)
- **Environmental tracking**: Events and Environment entities

## Usage

```python
from metaseed import miappe

m = miappe()
inv = m.Investigation(unique_id="INV001", title="Drought study")
material = m.BiologicalMaterial(unique_id="BM001", organism="Zea mays")
obs_unit = m.ObservationUnit(unique_id="OU001", observation_unit_type="plant")
```
