# Darwin Core v1.0

Darwin Core is a biodiversity data standard maintained by Biodiversity Information Standards (TDWG). It provides a standardized vocabulary for sharing information about biological occurrences, including species observations, specimen records, and sampling events.

Darwin Core centers on the **Occurrence** entity - evidence of an organism at a particular place and time. It supports both observational data (human or machine observations) and physical specimens (preserved, fossil, or living).

The standard is widely adopted by biodiversity data aggregators including GBIF (Global Biodiversity Information Facility), iDigBio, and VertNet.

```mermaid
flowchart TB
    subgraph core["Core"]
        OCC[Occurrence]
        ORG[Organism]
        MS[MaterialSample]
    end

    subgraph event["Event Context"]
        EVT[Event]
        LOC[Location]
    end

    subgraph taxonomy["Taxonomy"]
        ID[Identification]
        TAX[Taxon]
    end

    subgraph extensions["Extensions"]
        MOF[MeasurementOrFact]
        GEO[GeologicalContext]
        RR[ResourceRelationship]
    end

    %% Occurrence relationships
    OCC --> EVT
    OCC --> ID
    OCC --> ORG

    %% Event relationships
    EVT --> LOC

    %% Identification relationships
    ID --> TAX

    classDef core fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef event fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef tax fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef ext fill:#fce4ec,stroke:#e91e63,stroke-width:2px

    class OCC,ORG,MS core
    class EVT,LOC event
    class ID,TAX tax
    class MOF,GEO,RR ext
```

## Entities

| Category | Entities |
|----------|----------|
| **Core** | Occurrence, Organism, MaterialSample |
| **Event Context** | Event, Location |
| **Taxonomy** | Identification, Taxon |
| **Extensions** | MeasurementOrFact, GeologicalContext, ResourceRelationship |

## Key Concepts

**Occurrence-centric**: Darwin Core is built around the Occurrence entity, which represents evidence of an organism at a specific location and time. Every record describes what was observed or collected, where, when, and by whom.

**Basis of Record**: Each occurrence has a basisOfRecord field that categorizes the type of evidence:

- `PreservedSpecimen` - Museum specimen
- `FossilSpecimen` - Paleontological specimen
- `LivingSpecimen` - Living collection specimen
- `HumanObservation` - Field observation by a person
- `MachineObservation` - Camera trap, acoustic sensor, etc.
- `MaterialSample` - DNA sample, tissue sample

**Taxonomic Identification**: Identifications link occurrences to taxa. Multiple identifications can exist for a single occurrence, representing different determinations over time. The Taxon entity holds the full taxonomic hierarchy from kingdom to subspecies.

**Location and Georeferencing**: The Location entity captures both named places (country, state, locality) and coordinates (decimal latitude/longitude). It supports uncertainty measures and different coordinate systems for georeferencing quality assessment.

## Validation Rules

The Darwin Core profile includes validation rules for:

- Coordinate ranges (latitude -90 to 90, longitude -180 to 180)
- Elevation and depth consistency (minimum cannot exceed maximum)
- Controlled vocabularies for basisOfRecord, occurrenceStatus, taxonRank
- Positive coordinate uncertainty values

### Cross-references

Seven fields declare what they point at, so a value naming nothing is reported rather than accepted as free text. They split by where the target lives:

| Field | Names | Resolves |
|---|---|---|
| `Event.occurrenceID`, `Identification.occurrenceID`, `Organism.occurrenceID` | `Occurrence.occurrenceID` | in this dataset |
| `Location.eventID` | `Event.eventID` | in this dataset |
| `Event.parentEventID` | `Event.eventID` | outside it |
| `Taxon.acceptedNameUsageID`, `Taxon.parentNameUsageID` | `Taxon.taxonID` | outside it |

The last three are `reference_scope: external` ([Entity References](../api/schema-specs.md#references-that-resolve-outside-the-dataset)). A taxon's accepted or parent name usage is normally an identifier in GBIF's backbone or Catalogue of Life, and a survey commonly cites the campaign it belonged to without shipping it. Declared as plain references they would report correct data as broken; left undeclared, as they were, they were checked by nothing at all. Scoped external, a value that *does* name a record in the dataset is still checked, and one that does not is reported as not checked.

## Use Cases

- **Biodiversity databases**: GBIF, iDigBio, VertNet, ALA
- **Natural history collections**: Digitization and sharing of museum specimens
- **Citizen science**: iNaturalist, eBird observation records
- **Ecological research**: Species distribution modeling, conservation assessments
- **Environmental monitoring**: Long-term population and community studies

## Entity-Relationship Diagram

```mermaid
erDiagram
    Occurrence {
        string occurrenceID PK
        string basisOfRecord
        integer individualCount
        string sex
        string lifeStage
        string occurrenceStatus
        string recordedBy
    }

    Event {
        string eventID PK
        string occurrenceID FK
        string eventDate
        string habitat
        string samplingProtocol
    }

    Location {
        string locationID
        string eventID FK
        string country
        string stateProvince
        string locality
        float decimalLatitude
        float decimalLongitude
        string geodeticDatum
    }

    Identification {
        string identificationID
        string occurrenceID FK
        string identifiedBy
        string dateIdentified
        string identificationVerificationStatus
    }

    Taxon {
        string taxonID PK
        string identificationID FK
        string scientificName
        string kingdom
        string phylum
        string class
        string order
        string family
        string genus
        string taxonRank
    }

    Organism {
        string organismID PK
        string occurrenceID FK
        string organismName
        string organismScope
    }

    MaterialSample {
        string materialSampleID PK
        string preparations
        string disposition
    }

    MeasurementOrFact {
        string measurementID
        string measurementType
        string measurementValue
        string measurementUnit
    }

    GeologicalContext {
        string geologicalContextID
        string earliestEonOrLowestEonothem
        string latestEraOrHighestErathem
        string formation
    }

    ResourceRelationship {
        string resourceRelationshipID
        string resourceID FK
        string relatedResourceID FK
        string relationshipOfResource
    }

    Occurrence ||--o| Event : event
    Occurrence ||--o{ Identification : identifications
    Occurrence ||--o| Organism : organism
    Event ||--o| Location : location
    Identification ||--o| Taxon : taxon
```

## References

| Resource | URL |
|----------|-----|
| Darwin Core Standard | <https://dwc.tdwg.org/> |
| Darwin Core Terms | <https://dwc.tdwg.org/terms/> |
| TDWG (Biodiversity Information Standards) | <https://www.tdwg.org/> |
| GBIF (uses Darwin Core) | <https://www.gbif.org/> |
| Darwin Core GitHub | <https://github.com/tdwg/dwc> |

## Usage

```python
from metaseed import darwin_core

dwc = darwin_core()

# Create Occurrence
occurrence = dwc.Occurrence(
    occurrenceID="urn:catalog:UWBM:Bird:89776",
    basisOfRecord="HumanObservation",
    individualCount=1,
    occurrenceStatus="present",
    recordedBy="John Smith"
)

# Create Event linked to Occurrence
event = dwc.Event(
    eventID="EVT-2024-001",
    occurrenceID="urn:catalog:UWBM:Bird:89776",
    eventDate="2024-06-15",
    samplingProtocol="point count"
)

# Create Location linked to Event
location = dwc.Location(
    locationID="LOC-001",
    eventID="EVT-2024-001",
    decimalLatitude=45.5231,
    decimalLongitude=-122.6765,
    geodeticDatum="WGS84",
    country="United States",
    locality="Forest Park"
)
```
