# Schema Specifications

Schema specifications define the structure of MIAPPE-compliant metadata using YAML files.

## Overview

Each schema spec file describes:

- Field names and descriptions
- Data types and constraints
- Cardinality (required/optional, single/multiple)
- Ontology term references

## Specification Format

```yaml
name: Investigation
version: "1.1"
ontology_term: MIAPPE:Investigation
description: A MIAPPE investigation representing a phenotyping project

fields:
  - name: investigation_unique_id
    type: string
    required: true
    description: Unique identifier for the investigation
    ontology_term: MIAPPE:0000001

  - name: investigation_title
    type: string
    required: true
    description: Human-readable title
    ontology_term: MIAPPE:0000002

  - name: investigation_description
    type: string
    required: false
    description: Detailed description of the investigation
```

## Supported Types

| Type | Description |
|------|-------------|
| `string` | Text value |
| `integer` | Whole number |
| `float` | Decimal number |
| `boolean` | True/false |
| `date` | ISO 8601 date |
| `datetime` | ISO 8601 datetime |
| `uri` | Valid URI/URL |
| `ontology_term` | Reference to an ontology term |
| `list` | Collection of items (with `items` specifying element type) |
| `entity` | Reference to another entity (with `items` specifying entity type) |

## Entity References

Fields can reference other entities using the `entity` type with an `items` attribute:

```yaml
- name: geographic_location
  type: entity
  items: Location
  required: false
  description: Geographic location of the study.
```

This pattern enables proper relationship modeling between entities. For example:

- **MIAPPE**: `Study.geographic_location` references a `Location` entity
- **MIAPPE**: `BiologicalMaterial.material_source` references a `MaterialSource` entity
- **ISA**: `Sample.derives_from` references a `Source` entity

## Profiles

### MIAPPE v1.1

The MIAPPE profile supports 14 entities for plant phenotyping metadata:

- Investigation, Study, Person, BiologicalMaterial, MaterialSource, Sample
- ObservationUnit, ObservedVariable, Factor, FactorValue
- Event, Environment, DataFile, Location

Key entity relationships:

- `Study.geographic_location` -> `Location`
- `BiologicalMaterial.material_source` -> `MaterialSource`
- `Sample` -> `ObservationUnit` (via `observation_unit_id`)

### ISA v1.0

The ISA (Investigation/Study/Assay) profile supports experimental metadata:

- Investigation, Study, Assay, Person, Publication, Protocol
- Source, Sample, Extract, LabeledExtract, DataFile
- OntologyAnnotation, OntologySource, Comment

#### ISA Material Flow Chain

The ISA specification models material derivation using `derives_from` fields:

```
Source (origin material)
   |
   v derives_from
Sample (collected from source)
   |
   v derives_from
Extract (extracted material)
   |
   v derives_from
LabeledExtract (labeled for assay)
   |
   v derives_from
DataFile (measurement data)
```

This chain enables traceability from raw data back to the original source material.

Version-specific specs are stored under `src/miappe_api/specs/`.

## See Also

- [Model Factory](model-factory.md) - How specs become Pydantic models
- [MIAPPE Standard](https://www.miappe.org/) - Official MIAPPE documentation
