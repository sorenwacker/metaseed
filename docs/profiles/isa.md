# ISA v1.0

The Investigation-Study-Assay (ISA) framework is a metadata standard for describing life science experiments. It was developed to enable consistent reporting of multi-omics experiments including genomics, transcriptomics, proteomics, and metabolomics.

ISA models experiments as a hierarchy: an **Investigation** contains one or more **Studies**, each of which contains one or more **Assays**. Material flows through the experiment via a directed acyclic graph of **Processes**, where biological samples are transformed from sources to extracts to labeled extracts, eventually producing data files.

The framework is widely adopted in bioinformatics and supported by tools like ISA-Tools and repositories like MetaboLights and ArrayExpress.

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

    %% Investigation relationships
    INV --> STU
    INV --> PER
    INV --> PUB
    INV --> OS

    %% Study relationships
    STU --> ASS
    STU --> PROT
    STU --> SRC
    STU --> SAM
    STU --> SF
    STU --> PROC
    STU -.->|contacts| PER
    STU -.->|publications| PUB

    %% Protocol relationships
    PROT --> PP

    %% Assay relationships
    ASS --> DF
    ASS --> PROC
    ASS -.->|samples| SAM

    %% Process relationships (connect sources to samples)
    PROC --> PV
    PROC -.->|executes_protocol| PROT
    PROC -.->|inputs| SRC
    PROC -.->|outputs| SAM

    %% Material derivation chain
    SAM -.->|derives_from| SRC
    EXT -.->|derives_from| SAM
    LEXT -.->|derives_from| EXT

    %% Material characteristics
    SRC --> CHAR
    SAM --> CHAR
    SAM --> FV
    EXT --> CHAR
    LEXT --> CHAR

    %% DataFile provenance
    DF -.->|generated_from| SAM
    DF -.->|derives_from| LEXT

    %% Factor relationships
    SF --> FV
    FV -.->|factor_name| SF

    %% ParameterValue relationships
    PV -.->|category| PP

    %% Ontology relationships
    STU -.->|design_descriptors| OA
    ASS -.->|measurement_type| OA
    ASS -.->|technology_type| OA
    PER -.->|roles| OA
    PUB -.->|status| OA
    PROT -.->|protocol_type| OA
    PROT -.->|components| OA
    PP -.->|parameter_name| OA
    LEXT -.->|label| OA
    SF -.->|factor_type| OA
    FV -.->|unit| OA
    CHAR -.->|category| OA
    CHAR -.->|unit| OA
    PV -.->|unit| OA
    OA -.->|term_source| OS

    %% Comment relationships (all entities have comments)
    INV -.-> COM
    STU -.-> COM
    ASS -.-> COM
    PER -.-> COM
    PUB -.-> COM
    PROT -.-> COM
    PP -.-> COM
    SRC -.-> COM
    SAM -.-> COM
    EXT -.-> COM
    LEXT -.-> COM
    SF -.-> COM
    FV -.-> COM
    CHAR -.-> COM
    PV -.-> COM
    PROC -.-> COM
    DF -.-> COM
    OA -.-> COM
    OS -.-> COM

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

## Entity-Relationship Diagram

The following ERD shows all 121 fields across the 20 ISA entities: 53 scalar fields shown in entity boxes, 68 relationship fields shown as lines between entities. Fields marked with `PK` are primary keys.

```mermaid
erDiagram
    Investigation {
        string identifier PK
        string title
        string description
        date submission_date
        date public_release_date
        string filename
    }

    Study {
        string identifier PK
        string title
        string description
        date submission_date
        date public_release_date
        string filename
    }

    Assay {
        string filename PK
        string technology_platform
    }

    Person {
        string last_name PK
        string first_name
        string mid_initials
        string email
        string phone
        string fax
        string address
        string affiliation
    }

    Publication {
        string pubmed_id
        string doi
        string author_list
        string title PK
    }

    Protocol {
        string name PK
        string description
        uri uri
        string version
    }

    ProtocolParameter {
    }

    Source {
        string name PK
    }

    Sample {
        string name PK
    }

    Extract {
        string name PK
    }

    LabeledExtract {
        string name PK
    }

    StudyFactor {
        string name PK
    }

    FactorValue {
        string value
    }

    Characteristic {
        string value
    }

    ParameterValue {
        string value
    }

    Process {
        string name
        string performer
        date date
        list inputs
        list outputs
    }

    DataFile {
        string filename PK
        string label
    }

    OntologyAnnotation {
        string term PK
        string term_accession
    }

    OntologySource {
        string name PK
        string file
        string version
        string description
    }

    Comment {
        string name PK
        string value
    }

    Investigation ||--o{ Study : studies
    Investigation ||--o{ Person : contacts
    Investigation ||--o{ Publication : publications
    Investigation ||--o{ OntologySource : ontology_source_references
    Investigation ||--o{ Comment : comments

    Study ||--o{ Assay : assays
    Study ||--o{ Protocol : protocols
    Study ||--o{ Source : sources
    Study ||--o{ Sample : samples
    Study ||--o{ StudyFactor : factors
    Study ||--o{ Process : process_sequence
    Study ||--o{ Person : contacts
    Study ||--o{ Publication : publications
    Study ||--o{ OntologyAnnotation : design_descriptors
    Study ||--o{ Comment : comments

    Assay ||--o{ DataFile : data_files
    Assay ||--o{ Process : process_sequence
    Assay ||--o{ Sample : samples
    Assay ||--o| OntologyAnnotation : measurement_type
    Assay ||--o| OntologyAnnotation : technology_type
    Assay ||--o{ Comment : comments

    Person ||--o{ OntologyAnnotation : roles
    Person ||--o{ Comment : comments

    Publication ||--o| OntologyAnnotation : status
    Publication ||--o{ Comment : comments

    Protocol ||--o{ ProtocolParameter : parameters
    Protocol ||--o| OntologyAnnotation : protocol_type
    Protocol ||--o{ OntologyAnnotation : components
    Protocol ||--o{ Comment : comments

    ProtocolParameter ||--o| OntologyAnnotation : parameter_name
    ProtocolParameter ||--o{ Comment : comments

    Source ||--o{ Characteristic : characteristics
    Source ||--o{ Comment : comments

    Sample ||--o{ Characteristic : characteristics
    Sample ||--o{ FactorValue : factor_values
    Sample ||--o{ Source : derives_from
    Sample ||--o{ Comment : comments

    Extract ||--o{ Characteristic : characteristics
    Extract ||--o{ Sample : derives_from
    Extract ||--o{ Comment : comments

    LabeledExtract ||--o{ Characteristic : characteristics
    LabeledExtract ||--o{ Extract : derives_from
    LabeledExtract ||--o| OntologyAnnotation : label
    LabeledExtract ||--o{ Comment : comments

    StudyFactor ||--o| OntologyAnnotation : factor_type
    StudyFactor ||--o{ Comment : comments

    FactorValue ||--o| StudyFactor : factor_name
    FactorValue ||--o| OntologyAnnotation : unit
    FactorValue ||--o{ Comment : comments

    Characteristic ||--o| OntologyAnnotation : category
    Characteristic ||--o| OntologyAnnotation : unit
    Characteristic ||--o{ Comment : comments

    ParameterValue ||--o| ProtocolParameter : category
    ParameterValue ||--o| OntologyAnnotation : unit
    ParameterValue ||--o{ Comment : comments

    Process ||--o| Protocol : executes_protocol
    Process ||--o{ ParameterValue : parameter_values
    Process ||--o{ Comment : comments

    DataFile ||--o{ Sample : generated_from
    DataFile ||--o{ LabeledExtract : derives_from
    DataFile ||--o{ Comment : comments

    OntologyAnnotation ||--o| OntologySource : term_source
    OntologyAnnotation ||--o{ Comment : comments

    OntologySource ||--o{ Comment : comments
```

## Key Concepts

**Process-centric workflow**: ISA models experiments as directed acyclic graphs where each node is a Process that transforms inputs into outputs. This captures the provenance of how data was generated from original biological material.

**Material flow chain**: Biological material follows a transformation path: Source (original organism/specimen) → Sample (collected material) → Extract (isolated component) → LabeledExtract (prepared for measurement) → DataFile (measurement results).

**Protocol-driven**: Every Process references a Protocol that describes how the transformation was performed, including parameters and their values. This ensures reproducibility.

**Ontology annotations**: Fields can be annotated with OntologyAnnotation to provide semantic meaning using controlled vocabularies from OntologySource references.

## The Experimental Graph

ISA models experiments as a directed acyclic graph where **Process** nodes connect materials:

```
Source → Process → Sample → Process → Extract → Process → LabeledExtract → Process → DataFile
```

Key points:

- **All Sources and Samples MUST be declared at Study level** in `study.sources` and `study.samples`
- **Sample.derivesFrom** provides direct linkage from sample to source(s)
- **Process.inputs** references Sources or Samples by name
- **Process.outputs** references Samples or other materials by name
- **Process.executes_protocol** links to the Protocol describing the method

The process sequence captures the workflow and provenance, while samples maintain a direct `derivesFrom` reference to their source materials.

## References

Official ISA specifications and resources:

| Resource | URL |
|----------|-----|
| ISA Model Specification | <https://isa-specs.readthedocs.io/en/latest/isamodel.html> |
| ISA-JSON Format | <https://isa-specs.readthedocs.io/en/latest/isajson.html> |
| ISA-Tab Format | <https://isa-specs.readthedocs.io/en/latest/isatab.html> |
| ISA Tools (Python) | <https://github.com/ISA-tools/isa-api> |
| ISA Commons | <https://www.isacommons.org/> |

## Usage

```python
from metaseed import isa

i = isa()
source = i.Source(unique_id="SRC001", name="Patient 1")
sample = i.Sample(unique_id="SAM001", name="Blood sample", derives_from=[source])
```
