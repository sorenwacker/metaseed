# ISA vs MIAPPE Comparison

## Entity Comparison

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

    INV --> STU
    INV --> PER
    STU --> FAC
    FAC --> FV

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

    STU --> BM
    STU --> OU
    STU --> OV
    STU --> EVT
    STU --> ENV
    OU --> SAM
    BM --> MS
    STU -.-> LOC

    classDef shared fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef isa fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef miappe fill:#fff3e0,stroke:#ff9800,stroke-width:2px

    class INV,STU,PER,SAM,FAC,FV,DF shared
    class ASS,PROT,PP,SRC,EXT,LEXT,PROC,OA,OS,CHAR,PV,PUB_ISA,COM isa
    class BM,OU,OV,EVT,ENV,LOC,MS miappe
```

## Workflow Models

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

## Summary

| Aspect | ISA | MIAPPE |
|--------|-----|--------|
| **Entities** | 20 | 14 |
| **Focus** | Multi-omics, process workflows | Plant phenotyping, field trials |
| **Model** | Process-centric (DAG) | Observation-centric |
| **Person** | `first_name` + `last_name` | `name` |
| **Publication** | Structured entity | URL list |

## When to Use

| Use Case | Profile |
|----------|---------|
| Multi-omics (genomics, proteomics, metabolomics) | `isa` |
| Plant phenotyping, field trials | `miappe` |
| Both multi-omics and phenotyping | `isa-miappe-combined` |
