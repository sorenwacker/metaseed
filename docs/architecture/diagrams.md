# Data Model Diagrams

Visual reference for profile data models.

## ISA v1.0

20 entities for life science experiments with process-centric workflows.

```mermaid
flowchart TB
    subgraph core["Core"]
        INV[Investigation]
        STU[Study]
        ASS[Assay]
        PER[Person]
        PUB[Publication]
    end

    subgraph protocol["Protocols"]
        PROT[Protocol]
        PP[ProtocolParameter]
    end

    subgraph material["Material Flow"]
        SRC[Source]
        SAM[Sample]
        EXT[Extract]
        LEXT[LabeledExtract]
    end

    subgraph process["Process Graph"]
        PROC[Process]
        PV[ParameterValue]
        CHAR[Characteristic]
    end

    subgraph factors["Factors"]
        SF[StudyFactor]
        FV[FactorValue]
    end

    subgraph ontology["Ontology"]
        OA[OntologyAnnotation]
        OS[OntologySource]
        COM[Comment]
    end

    subgraph output["Output"]
        DF[DataFile]
    end

    INV --> STU
    INV --> PER
    INV --> PUB
    STU --> ASS
    STU --> PROT
    STU --> SRC
    STU --> SF
    PROT --> PP
    SRC -->|Process| SAM
    SAM -->|Process| EXT
    EXT -->|Process| LEXT
    ASS --> PROC
    ASS --> DF
    PROC --> PV
    SF --> FV

    classDef core fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef prot fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef mat fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef proc fill:#fce4ec,stroke:#e91e63,stroke-width:2px
    classDef fac fill:#e0f2f1,stroke:#009688,stroke-width:2px
    classDef ont fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px
    classDef out fill:#eceff1,stroke:#607d8b,stroke-width:2px

    class INV,STU,ASS,PER,PUB core
    class PROT,PP prot
    class SRC,SAM,EXT,LEXT mat
    class PROC,PV,CHAR proc
    class SF,FV fac
    class OA,OS,COM ont
    class DF out
```

---

## MIAPPE v1.1

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

---

## Profile Comparison

| Profile | Entities | Focus |
|---------|----------|-------|
| ISA v1.0 | 20 | Multi-omics, process workflows |
| MIAPPE v1.1 | 14 | Plant phenotyping, field trials |
| Combined v1.0 | 25 | Unified ISA + MIAPPE |
| Combined v2.0 | 26 | + Experiment entity, reference model |

### ISA vs MIAPPE Workflow Models

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

---

## ISA-MIAPPE-Combined v1.0

25 entities combining ISA and MIAPPE.

```mermaid
flowchart TB
    subgraph shared["Shared Core (7)"]
        INV[Investigation]
        STU[Study]
        PER[Person]
        SAM[Sample]
        FAC[Factor]
        FV[FactorValue]
        DF[DataFile]
    end

    subgraph isa["ISA Extensions (12)"]
        ASS[Assay]
        PROT[Protocol]
        PP[ProtocolParameter]
        SRC[Source]
        EXT[Extract]
        LEXT[LabeledExtract]
        PROC[Process]
        PV[ParameterValue]
        CHAR[Characteristic]
        PUB[Publication]
        OA[OntologyAnnotation]
        OS[OntologySource]
    end

    subgraph miappe["MIAPPE Extensions (6)"]
        BM[BiologicalMaterial]
        OU[ObservationUnit]
        OV[ObservedVariable]
        EVT[Event]
        ENV[Environment]
        MS[MaterialSource]
    end

    INV --> STU
    INV --> PER
    INV --> PUB
    STU --> ASS
    STU --> PROT
    STU --> SRC
    STU --> FAC
    STU --> BM
    STU --> OU
    STU --> OV
    STU --> EVT
    STU --> ENV
    PROT --> PP
    SRC -->|Process| SAM
    SAM -->|Process| EXT
    EXT -->|Process| LEXT
    ASS --> PROC
    ASS --> DF
    PROC --> PV
    FAC --> FV
    OU --> SAM
    BM --> MS

    classDef shared fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef isa fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef miappe fill:#fff3e0,stroke:#ff9800,stroke-width:2px

    class INV,STU,PER,SAM,FAC,FV,DF shared
    class ASS,PROT,PP,SRC,EXT,LEXT,PROC,PV,CHAR,PUB,OA,OS isa
    class BM,OU,OV,EVT,ENV,MS miappe
```

---

## ISA-MIAPPE-Combined v2.0

26 entities with new Experiment entity and reference-based ownership.

```mermaid
flowchart TB
    subgraph shared["Shared Core (7)"]
        INV[Investigation]
        STU[Study]
        EXP[Experiment]
        PER[Person]
        PUB[Publication]
        FAC[Factor]
        FV[FactorValue]
    end

    subgraph isa["ISA Extensions (9)"]
        ASS[Assay]
        PROT[Protocol]
        PP[ProtocolParameter]
        PROC[Process]
        PV[ParameterValue]
        SRC[Source]
        SAM[Sample]
        EXT[Extract]
        LEXT[LabeledExtract]
    end

    subgraph miappe["MIAPPE Extensions (5)"]
        BM[BiologicalMaterial]
        OU[ObservationUnit]
        OV[ObservedVariable]
        EVT[Event]
        ENV[Environment]
    end

    subgraph annotations["Shared Annotations (3)"]
        OA[OntologyAnnotation]
        OS[OntologySource]
        CHAR[Characteristic]
    end

    subgraph support["Support (2)"]
        MS[MaterialSource]
        DF[DataFile]
    end

    INV --> STU
    INV --> PER
    INV --> PUB
    STU --> EXP
    STU --> PROT
    STU --> FAC
    STU --> BM
    STU --> OU
    STU --> OV
    STU --> SAM
    EXP --> ASS
    EXP --> EVT
    EXP --> ENV
    EXP -.->|references| OU
    EXP -.->|references| SAM
    PROT --> PP
    SRC -->|Process| SAM
    SAM -->|Process| EXT
    EXT -->|Process| LEXT
    ASS --> PROC
    ASS --> DF
    PROC --> PV
    FAC --> FV
    BM --> MS

    classDef shared fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef isa fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef miappe fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef annot fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px
    classDef supp fill:#eceff1,stroke:#607d8b,stroke-width:2px

    class INV,STU,EXP,PER,PUB,FAC,FV shared
    class ASS,PROT,PP,PROC,PV,SRC,SAM,EXT,LEXT isa
    class BM,OU,OV,EVT,ENV miappe
    class OA,OS,CHAR annot
    class MS,DF supp
```

### v2.0 Ownership Model

```mermaid
flowchart LR
    subgraph study["Study OWNS (shared pool)"]
        direction TB
        BM[BiologicalMaterials]
        OU[ObservationUnits]
        SAM[Samples]
        OV[ObservedVariables]
        FAC[Factors]
        PROT[Protocols]
    end

    subgraph exp["Experiment OWNS (time/location specific)"]
        direction TB
        EVT[Events]
        ENV[Environments]
        ASS[Assays]
    end

    exp -.->|observation_unit_ids| OU
    exp -.->|sample_ids| SAM

    classDef owns fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef refs fill:#fff3e0,stroke:#ff9800,stroke-width:2px

    class BM,OU,SAM,OV,FAC,PROT owns
    class EVT,ENV,ASS refs
```
