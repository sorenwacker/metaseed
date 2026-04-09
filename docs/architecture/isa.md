# ISA v1.0

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
        CHAR[Characteristic]
    end

    subgraph process["Process Graph"]
        PROC[Process]
        PV[ParameterValue]
    end

    subgraph factors["Factors"]
        SF[StudyFactor]
        FV[FactorValue]
    end

    subgraph ontology["Ontology & Annotations"]
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
    INV --> OS
    STU --> ASS
    STU --> PROT
    STU --> SRC
    STU --> SF
    PROT --> PP
    SRC -->|Process| SAM
    SAM -->|Process| EXT
    EXT -->|Process| LEXT
    SRC --> CHAR
    SAM --> CHAR
    ASS --> PROC
    ASS --> DF
    PROC --> PV
    SF --> FV
    CHAR -.-> OA
    SF -.-> OA
    OA --> OS

    classDef core fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef prot fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef mat fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef proc fill:#fce4ec,stroke:#e91e63,stroke-width:2px
    classDef fac fill:#e0f2f1,stroke:#009688,stroke-width:2px
    classDef ont fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px
    classDef out fill:#eceff1,stroke:#607d8b,stroke-width:2px

    class INV,STU,ASS,PER,PUB core
    class PROT,PP prot
    class SRC,SAM,EXT,LEXT,CHAR mat
    class PROC,PV proc
    class SF,FV fac
    class OA,OS,COM ont
    class DF out
```

## Entities

| Category | Entities |
|----------|----------|
| **Core** | Investigation, Study, Assay, Person, Publication |
| **Protocols** | Protocol, ProtocolParameter |
| **Material Flow** | Source, Sample, Extract, LabeledExtract, Characteristic |
| **Process Graph** | Process, ParameterValue |
| **Factors** | StudyFactor, FactorValue |
| **Ontology** | OntologyAnnotation, OntologySource, Comment |
| **Output** | DataFile |

## Key Concepts

- **Process-centric**: Experiments modeled as directed acyclic graphs of processes
- **Material transformations**: Source → Sample → Extract → LabeledExtract → Data
- **Protocol-driven**: Every transformation references a protocol
- **Ontology-backed**: Terms annotated with OntologyAnnotation

## Usage

```python
from metaseed import isa

i = isa()
source = i.Source(unique_id="SRC001", name="Patient 1")
sample = i.Sample(unique_id="SAM001", name="Blood sample", derives_from=[source])
```
