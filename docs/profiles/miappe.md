# MIAPPE v1.1

MIAPPE (Minimum Information About Plant Phenotyping Experiments) is a metadata standard for describing plant phenotyping studies. It was developed by the plant science community to enable consistent reporting of field trials, greenhouse experiments, and growth chamber studies.

MIAPPE focuses on **observation units** (individual plants, plots, or samples) and the **observed variables** (traits) measured on them. It captures the biological materials used, environmental conditions, and experimental factors that may affect plant phenotypes.

The standard is maintained by the MIAPPE consortium and is widely used in plant research databases and breeding information systems.

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

    %% Investigation relationships
    INV --> STU
    INV --> PER

    %% Study relationships
    STU --> BM
    STU --> OU
    STU --> OV
    STU --> FAC
    STU --> EVT
    STU --> ENV
    STU --> DF
    STU --> PER
    STU --> LOC

    %% BiologicalMaterial relationships
    BM --> MS

    %% Factor relationships
    FAC --> FV
    FV -.->|factor_id| FAC

    %% ObservationUnit relationships
    OU --> SAM
    OU --> FV
    OU -.->|biological_material_id| BM

    %% Event relationships
    EVT -.->|observation_unit_ids| OU

    %% Sample relationships
    SAM -.->|observation_unit_id| OU

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

## Entity-Relationship Diagram

The following ERD shows all 138 fields across the 14 MIAPPE entities: 123 scalar fields shown in entity boxes, 15 relationship fields shown as lines between entities. Fields marked with `PK` are primary keys, `FK` indicates foreign keys.

```mermaid
erDiagram
    Investigation {
        string unique_id PK
        string title
        string description
        date submission_date
        date public_release_date
        uri license
        string miappe_version
        list associated_publications
    }

    Study {
        string unique_id PK
        string investigation_id FK
        string title
        string description
        datetime start_date
        datetime end_date
        string contact_institution
        string experimental_site_name
        float latitude
        float longitude
        float altitude
        string experimental_design_type
        string experimental_design_description
        list observation_unit_level_hierarchy
        string observation_unit_description
        string growth_facility_type
        string cultural_practices
        uri map_of_experimental_design
    }

    Person {
        string investigation_id FK
        string study_id FK
        string name PK
        string email
        string institution
        string role
        string orcid
    }

    BiologicalMaterial {
        string unique_id PK
        string study_id FK
        string organism
        string genus
        string species
        string infraspecific_name
        string accession_number
        string biological_material_description
        float biological_material_latitude
        float biological_material_longitude
        float biological_material_altitude
        string biological_material_coordinates_uncertainty
        string biological_material_preprocessing
        list external_references
    }

    ObservationUnit {
        string unique_id PK
        string study_id FK
        string observation_unit_type
        string biological_material_id FK
        string spatial_distribution_type
        string spatial_distribution
        string observation_unit_x_ref
        string observation_unit_y_ref
        string observation_unit_block
        string observation_unit_replicate
        string entry_type
        string observation_level
        string observation_level_code
        list external_references
    }

    ObservedVariable {
        string unique_id PK
        string study_id FK
        string name
        string trait
        string trait_accession_number
        string trait_description
        string method
        string method_accession_number
        string method_description
        string scale
        string scale_accession_number
        string scale_description
        string time_scale
        uri reference
    }

    Factor {
        string unique_id PK
        string study_id FK
        string name
        string description
        string factor_type
    }

    FactorValue {
        string unique_id PK
        string factor_id FK
        string value
        string description
    }

    Event {
        string unique_id PK
        string study_id FK
        string event_type
        datetime date
        datetime end_date
        string description
        list observation_unit_ids
        string event_accession_number
    }

    Environment {
        string unique_id PK
        string study_id FK
        string parameter
        string parameter_accession_number
        string value
        string unit
        datetime date
        string description
    }

    Sample {
        string unique_id PK
        string observation_unit_id FK
        string plant_structural_development_stage
        string plant_anatomical_entity
        datetime collection_date
        string description
        list external_references
    }

    DataFile {
        string unique_id PK
        string study_id FK
        string name
        uri link
        string description
        string version
        string file_type
    }

    Location {
        string unique_id PK
        string study_id FK
        string name
        string abbreviation
        string country
        string country_code
        float latitude
        float longitude
        float altitude
        string description
        string address
        string location_type
    }

    MaterialSource {
        string unique_id PK
        string name
        string description
        string institute_code
        string country
        string address
        float latitude
        float longitude
    }

    Investigation ||--o{ Study : contains
    Investigation ||--o{ Person : contacts
    Study ||--o{ Person : persons
    Study ||--o| Location : geographic_location
    Study ||--o{ DataFile : data_files
    Study ||--o{ BiologicalMaterial : biological_materials
    Study ||--o{ ObservationUnit : observation_units
    Study ||--o{ ObservedVariable : observed_variables
    Study ||--o{ Factor : factors
    Study ||--o{ Event : events
    Study ||--o{ Environment : environments
    BiologicalMaterial ||--o| MaterialSource : material_source
    ObservationUnit ||--o{ Sample : samples
    ObservationUnit ||--o{ FactorValue : factor_values
    ObservationUnit }o--|| BiologicalMaterial : biological_material_id
    Factor ||--o{ FactorValue : values
    FactorValue }o--|| Factor : factor_id
    Event }o--o{ ObservationUnit : observation_unit_ids
    Sample }o--|| ObservationUnit : observation_unit_id
```

## Key Concepts

**Observation-centric**: Unlike ISA's process workflows, MIAPPE centers on ObservationUnits - the things being measured. An observation unit can be a single plant, a pot, a plot, or any grouping of plants that receives the same treatment and is measured together.

**Biological material**: Plants are described through BiologicalMaterial entities that capture species, accession, and origin information. MaterialSource tracks where the genetic material came from (seed bank, collection site, etc.).

**Observed variables**: Measurements are defined by ObservedVariable entities using a trait/method/scale triplet. The trait describes what is measured (e.g., "plant height"), the method describes how (e.g., "ruler measurement"), and the scale describes the units and range (e.g., "centimeters, 0-300").

**Environmental context**: Event entities track things that happen during the experiment (planting, irrigation, harvest). Environment entities describe growth conditions (temperature, humidity, light).

## Entity Linking

Every nested entity includes a **parent reference field** that links it to its container. This enables:

- Round-trip Excel export/import without losing relationships
- Flat tabular representation for spreadsheet workflows
- Cross-entity validation and referential integrity

| Entity | Parent Field | Description |
|--------|--------------|-------------|
| Study | `investigation_id` | Links to parent Investigation |
| Person | `investigation_id` or `study_id` | Links to Investigation (as contact) or Study (as personnel) |
| BiologicalMaterial | `study_id` | Links to parent Study |
| ObservationUnit | `study_id` | Links to parent Study |
| ObservedVariable | `study_id` | Links to parent Study |
| Factor | `study_id` | Links to parent Study |
| FactorValue | `factor_id` | Links to parent Factor |
| Event | `study_id` | Links to parent Study |
| Environment | `study_id` | Links to parent Study |
| DataFile | `study_id` | Links to parent Study |
| Location | `study_id` | Links to parent Study |
| Sample | `observation_unit_id` | Links to parent ObservationUnit |

## Usage

```python
from metaseed import miappe

m = miappe()

# Create Investigation
inv = m.Investigation(unique_id="INV001", title="Drought study")

# Create Study linked to Investigation
study = m.Study(
    unique_id="STU001",
    investigation_id="INV001",
    title="Field trial 2024"
)

# Create BiologicalMaterial linked to Study
material = m.BiologicalMaterial(
    unique_id="BM001",
    study_id="STU001",
    organism="Zea mays"
)

# Create ObservationUnit linked to Study
obs_unit = m.ObservationUnit(
    unique_id="OU001",
    study_id="STU001",
    observation_unit_type="plant"
)
```
