# ISA and MIAPPE Comparison

This document compares the ISA (Investigation-Study-Assay) and MIAPPE (Minimum Information About Plant Phenotyping Experiments) metadata standards, highlighting their shared concepts and domain-specific extensions.

## Overview

Both standards follow a hierarchical structure for organizing experimental metadata:

- **ISA**: General-purpose framework for life science experiments, with emphasis on assay workflows and data provenance
- **MIAPPE**: Plant phenotyping-specific standard, with emphasis on field trials, germplasm, and environmental conditions

## Entity Comparison Diagram

```mermaid
flowchart TB
    subgraph shared["Shared Concepts"]
        direction TB
        INV[Investigation]
        STU[Study]
        PER[Person/Contact]
        SAM[Sample]
        FAC[Factor/StudyFactor]
        FV[FactorValue]
        DF[DataFile]
    end

    subgraph isa["ISA-Specific"]
        direction TB
        ASS[Assay]
        PROT[Protocol]
        PP[ProtocolParameter]
        SRC[Source]
        EXT[Extract]
        LEXT[LabeledExtract]
        PROC[Process]
        OA[OntologyAnnotation]
        OS[OntologySource]
        CHAR[Characteristic]
        PV[ParameterValue]
        PUB_ISA[Publication]
        UNIT[Unit]
        COM[Comment]
    end

    subgraph miappe["MIAPPE-Specific"]
        direction TB
        BM[BiologicalMaterial]
        OU[ObservationUnit]
        OV[ObservedVariable]
        EVT[Event]
        ENV[Environment]
        LOC[Location]
        MS[MaterialSource]
    end

    %% Core hierarchy (both standards)
    INV --> STU
    INV --> PER
    STU --> FAC
    FAC --> FV

    %% ISA relationships
    STU --> ASS
    ASS --> DF
    ASS --> PROC
    STU --> PROT
    PROT --> PP
    STU --> SRC
    SRC -->|Process| SAM
    SAM -->|Process| EXT
    EXT -->|Process| LEXT
    PROC --> PV
    INV --> PUB_ISA

    %% MIAPPE relationships
    STU --> BM
    STU --> OU
    STU --> OV
    STU --> EVT
    STU --> ENV
    OU --> SAM
    BM --> MS
    STU -.-> LOC

    %% Styling
    classDef shared fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef isa fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef miappe fill:#fff3e0,stroke:#ff9800,stroke-width:2px

    class INV,STU,PER,SAM,FAC,FV,DF shared
    class ASS,PROT,PP,SRC,EXT,LEXT,PROC,OA,OS,CHAR,PV,PUB_ISA,UNIT,COM isa
    class BM,OU,OV,EVT,ENV,LOC,MS miappe
```

## Detailed Comparison

### Shared Core Entities

| Concept | ISA | MIAPPE | Notes |
|---------|-----|--------|-------|
| **Investigation** | `Investigation` | `Investigation` | Entry point; contains overall experimental context |
| **Study** | `Study` | `Study` | Central unit; defines experimental design |
| **Person** | `Person` (last_name, first_name) | `Person` (name) | Contact information; ISA splits name fields |
| **Sample** | `Sample` | `Sample` | Material collected from observation units/subjects |
| **Factor** | `StudyFactor` | `Factor` | Independent variables manipulated in experiment |
| **FactorValue** | `FactorValue` | `FactorValue` | Specific factor levels/treatments |
| **DataFile** | `DataFile` | `DataFile` | Output data files (tabular, images, etc.) |

!!! note "Publication Handling"
    ISA has a structured `Publication` entity with PubMed ID, DOI, author list, and status.
    MIAPPE uses a simple list of DOIs/URLs in `associated_publications`.

### ISA-Specific Entities

| Entity | Purpose |
|--------|---------|
| **Assay** | Test performed on samples producing qualitative/quantitative measurements |
| **Protocol** | Experimental procedures with parameters and components |
| **Source** | Original biological material before any processing |
| **Extract** | Material extracted from samples (e.g., DNA, RNA, protein) |
| **LabeledExtract** | Labeled material for detection (e.g., fluorescent tags) |
| **Process** | Nodes in experimental workflow graph; links materials to protocols |
| **OntologyAnnotation** | Structured ontology term references with accession numbers |
| **OntologySource** | Provenance of ontology terms used in annotations |
| **Characteristic** | Material property qualifiers (organism, strain, etc.) |
| **ParameterValue** | Values for protocol parameters in process instances |
| **Unit** | Dimensional data classification (e.g., mg, mL, hours) |
| **Publication** | Structured publication metadata (PubMed ID, DOI, authors) |
| **Comment** | Free-text key-value annotations |

### MIAPPE-Specific Entities

| Entity | Purpose |
|--------|---------|
| **BiologicalMaterial** | Germplasm/plant material with accession info |
| **ObservationUnit** | Plot, plant, or pot being measured |
| **ObservedVariable** | Trait + Method + Scale (measurement definition) |
| **Event** | Discrete occurrences (sowing, harvest, treatment) |
| **Environment** | Environmental parameter recordings |
| **Location** | Geographic site information |
| **MaterialSource** | Genebank or institution providing material |

## Structural Differences

```mermaid
flowchart LR
    subgraph isa_flow["ISA: Process-Centric"]
        S1[Source] --> P1[Process] --> S2[Sample]
        S2 --> P2[Process] --> E1[Extract]
        E1 --> P3[Process] --> D1[Data]
    end

    subgraph miappe_flow["MIAPPE: Observation-Centric"]
        BM1[BiologicalMaterial] --> OU1[ObservationUnit]
        OU1 --> OBS[Observations]
        OBS --> VAR[ObservedVariable]
        EVT1[Events] --> OU1
        ENV1[Environment] --> OU1
    end
```

### ISA Approach
- Models experiments as **directed acyclic graphs** of processes
- Tracks material transformations (Source -> Sample -> Extract -> Data)
- Protocol-centric: every transformation references a protocol
- Supports complex multi-omics workflows

### MIAPPE Approach
- Models experiments as **observation units** with measurements
- Field trial-oriented: plots, blocks, replicates
- Trait-centric: measurements defined by trait/method/scale
- Includes environmental and event tracking

## Mapping Between Standards

When converting between ISA and MIAPPE:

| ISA Concept | MIAPPE Equivalent | Mapping Notes |
|-------------|-------------------|---------------|
| Source | BiologicalMaterial | ISA Source ~ MIAPPE germplasm |
| Sample | Sample or ObservationUnit | Depends on context |
| Assay | Study + ObservedVariable | MIAPPE doesn't separate assays |
| Protocol | Event or cultural_practices | Less structured in MIAPPE |
| Characteristic | BiologicalMaterial fields | Organism, genus, species, etc. |
| Process | Event | MIAPPE events are simpler |

## When to Use Each Standard

**Use ISA when:**

- Working with multi-omics data (genomics, proteomics, metabolomics)
- Need detailed protocol documentation
- Tracking complex sample processing workflows
- Integrating with ISA-Tab ecosystem tools

**Use MIAPPE when:**

- Conducting plant phenotyping experiments
- Managing field trial data
- Need germplasm/accession tracking
- Working with BrAPI-compatible systems
- Environmental data is important

**Use Combined when:**

- Need both multi-omics and phenotyping capabilities
- Conducting integrated plant research (phenomics + genomics/transcriptomics)
- Want a single unified schema for diverse experimental data

!!! warning "Experimental"
    The combined profile (`combined_v1.0.yaml`) is experimental and merges ISA and MIAPPE entities into a unified model. It uses ISA-style `identifier` fields as the common naming convention.

## Combined Profile Usage

```python
from miappe_api.facade import ProfileFacade

# Load combined profile
combined = ProfileFacade("combined", "1.0")

# Create ISA entities
protocol = combined.Protocol(name="RNA Extraction", protocol_type="extraction")
assay = combined.Assay(filename="assay.txt", measurement_type="transcription profiling")

# Create MIAPPE entities
material = combined.BiologicalMaterial(identifier="BM-001", organism="Zea mays")
obs_unit = combined.ObservationUnit(identifier="OU-001", observation_unit_type="plant")

# Create shared entities
investigation = combined.Investigation(identifier="INV-001", title="Integrated Study")
```

## References

- [ISA Tools - Official Site](https://isa-tools.org/)
- [ISA Abstract Model Specification](https://isa-specs.readthedocs.io/en/latest/isamodel.html)
- [ISA-Tab Format Specification](https://isa-specs.readthedocs.io/en/latest/isatab.html)
- [MIAPPE Official Site](https://www.miappe.org/)
- [MIAPPE GitHub Repository](https://github.com/MIAPPE/MIAPPE)
- [MIAPPE 1.1 Paper (Papoutsoglou et al., 2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7317793/)
- [ISA-Tab for Plant Phenotyping (MIAPPE-ISA mapping)](https://github.com/MIAPPE/ISA-Tab-for-plant-phenotyping)
