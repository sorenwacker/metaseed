# Health-RI Core v2.0

The `health-ri-core` profile is the Health-RI core metadata schema, version 2.0.3, which the Dutch National Health Data Catalogue uses to describe datasets, their distributions and the services that serve them. It is a DCAT application profile: DCAT-AP 3, DCAT-AP NL and HealthDCAT-AP, as the SHACL shapes and the requirement spreadsheet in the [health-ri-metadata](https://github.com/Health-RI/health-ri-metadata) repository define them. Cardinality follows the shapes; whether a field is required, recommended or optional follows the spreadsheet.

A **`Catalog`** is the root. It names its publisher and contact point, and owns its datasets, dataset series and data services. A **`Dataset`** owns its distributions, identifiers, attributions, relationships, quality certificates and retention period, and names the catalogue it belongs to in `catalog_id`; a **`Distribution`** names its dataset in `dataset_id` and owns its checksum. Agents (an organisation or a person), contact details (`Kind`), periods and identifiers are value entities nested where they are used. Most text fields are lists, because DCAT allows a title or a description per language; most controlled values are IRIs from the EU vocabularies, DPV, IANA and SPDX.

## Entities

| Category | Entities |
|----------|----------|
| **Catalogue** | Catalog, DatasetSeries |
| **Data** | Dataset, Distribution, DataService |
| **Provenance** | Agent, Attribution, Relationship, QualityCertificate, Identifier |
| **Values** | Kind, PeriodOfTime, Checksum |

## Entity-Relationship Diagram

```mermaid
erDiagram
    Catalog {
        string identifier
        list title
        list description
        uri homepage
        date release_date
    }
    Dataset {
        string identifier
        string catalog_id
        list title
        list description
        uri access_rights
        list keyword
        list theme
    }
    Distribution {
        string identifier
        string dataset_id
        list title
        uri access_url
        integer byte_size
        uri format
        uri license
    }
    DataService {
        string identifier
        string catalog_id
        list title
        uri endpoint_url
        uri endpoint_description
    }
    DatasetSeries {
        string identifier
        string catalog_id
        list title
    }
    Agent {
        list name
        list agent_identifier
        string email
        uri homepage
    }
    Kind {
        string has_email
        string formatted_name
    }
    PeriodOfTime {
        date start_date
        date end_date
    }
    Identifier {
        string notation
    }
    Attribution {
        string identifier
        string dataset_id
    }
    Relationship {
        string dataset_id
        list had_role
        list relation
    }
    QualityCertificate {
        string dataset_id
    }
    Checksum {
        string distribution_id
        uri algorithm
        string checksum_value
    }

    Catalog ||--o{ Dataset : dataset
    Catalog ||--o{ DatasetSeries : dataset_series
    Catalog ||--o{ DataService : service
    Catalog ||--o{ Agent : creator
    Dataset ||--o{ Distribution : distribution
    Dataset ||--o{ Agent : creator
    Dataset ||--o{ Identifier : other_identifier
    Dataset ||--o{ Attribution : qualified_attribution
    Dataset ||--o{ Relationship : qualified_relation
    Dataset ||--o{ QualityCertificate : quality_annotation
    Dataset }o--|| Catalog : catalog_id
    Distribution }o--|| Dataset : dataset_id
    Checksum }o--|| Distribution : distribution_id
```

## How the profile follows the SHACL shapes

The schema is published as one SHACL node shape per class (`Formalisation(shacl)/Core/PiecesShape/*.ttl` in the [health-ri-metadata](https://github.com/Health-RI/health-ri-metadata) repository). The profile was checked against them property by property on 261001, and the shapes as recorded that day are kept under `tests/fixtures/health_ri_shapes/`, where `tests/test_health_ri_core_profile.py` holds the profile to them:

- **Every property a shape names is a field** of the entity with the shape's name. The 13 shapes name 143 properties; the profile has a field for each.
- **Cardinality follows the shape.** A property with `sh:minCount 1` is a required field, any other is optional. The one discrepancy the check found, a contact point required on a catalogue where the shape sets no minimum, was corrected.
- **A field is named after the RDF term**, in snake case, not after the shape's `sh:name` label. The two differ in nine places, and the test carries the map: `agent_identifier` (`dct:identifier`, labelled *identifier*) and `homepage` (`foaf:homepage`, labelled *url*) on Agent; `homepage`, `license` and `theme_taxonomy` on Catalog (labelled *home page*, *licence*, *themes*); `conforms_to`, `endpoint_description` and `endpoint_url` on DataService (labelled *application profile*, *end point description*, *end point URL*); and `number_of_unique_individuals` on Dataset, whose shape label reads *infividuals*.
- **Requirement tier** (`required`, `recommended`, `optional` on each field) follows the requirement level in the schema's spreadsheet, `Documents/Metadata_CoreGenericHealth_v2.xlsx`, which is where the schema states what a catalogue should supply beyond what the shapes enforce.

Three things the profile adds that no shape names, because metaseed needs a tree of records where SHACL describes a graph of IRIs: the `catalog_id`, `dataset_id` and `distribution_id` fields that name a child's parent; a local `identifier` on each resource the shapes identify by its IRI alone (Catalog, Dataset, Distribution, DataService, DatasetSeries, Attribution), which is what the parent fields point at; and the `dataset_series` list on Catalog that nests dataset series under the catalogue that lists them. The value entities (Kind, PeriodOfTime, Identifier, Checksum, Relationship, QualityCertificate) have exactly the shape's properties.

To follow a new release of the schema: re-record the shapes into the fixture directory, run the test, and make the profile match what it reports, under a new profile version.

## Usage

```python
from metaseed import health_ri_core

h = health_ri_core()

catalog = h.Catalog(
    identifier="https://example.org/catalog/example-umc-research",
    title=["Example UMC research data catalogue"],
    description=["Datasets of the Example University Medical Centre."],
    contact_point={"has_email": "datadesk@example.org", "formatted_name": "Example UMC Research Data Desk"},
    publisher={
        "name": ["Example University Medical Centre"],
        "agent_identifier": ["https://ror.org/00000example"],
        "email": "info@example.org",
        "homepage": "https://example.org",
    },
)
```

## References

| Resource | URL |
|----------|-----|
| Health-RI metadata schema | <https://github.com/Health-RI/health-ri-metadata> |
| National Health Data Catalogue | <https://www.health-ri.nl/en/services/national-health-data-catalogue> |
| HealthDCAT-AP | <https://healthdcat-ap.github.io/> |
| DCAT-AP 3 | <https://semiceu.github.io/DCAT-AP/releases/3.0.0/> |
