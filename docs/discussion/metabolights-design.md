# MetaboLights Profile Design

MetaboLights uses the ISA-Tab format with metabolomics-specific extensions. This document discusses design decisions made when adapting the MetaboLights schema for metaseed.

## Assay Type Hierarchy Problem

In ISA-Tab, assay types are distinguished by file naming and column headers, not by separate entity types. MetaboLights extends this with technology-specific columns for NMR, LC-MS, and GC-MS assays.

The conceptual hierarchy is:

```
Assay (base)
├── NMRAssay (NMR-specific fields)
├── LCMSAssay (LC-MS-specific fields)
└── GCMSAssay (GC-MS-specific fields)
```

### The Problem

Metaseed doesn't support entity inheritance. So how should specialized assay types relate to Study?

**Current implementation (problematic):**

```yaml
Study:
  fields:
    - name: assays
      type: list
      items: Assay  # Only generic Assay

NMRAssay:
  fields:
    - name: study_id
      reference: Study.identifier  # Reverse reference only
```

This creates disconnected specialized assays that don't appear in `Study.assays`.

### Design Options

#### Option A: Separate Lists Per Technology

Each technology gets its own list field in Study:

```yaml
Study:
  fields:
    - name: nmr_assays
      type: list
      items: NMRAssay
    - name: lcms_assays
      type: list
      items: LCMSAssay
    - name: gcms_assays
      type: list
      items: GCMSAssay
```

**Pros:**
- Clear which assay types a study contains
- Type-safe: each list only accepts its specific type
- Graph shows direct Study → AssayType relationships

**Cons:**
- More fields in Study entity
- Doesn't match ISA-Tab's single assay list concept
- Adding new assay types requires modifying Study

#### Option B: Remove Generic Assay

Delete the generic `Assay` entity and keep only specialized types:

```yaml
# No Assay entity
# No Study.assays field
# Specialized assays link back via study_id reference
```

**Pros:**
- Simpler model
- No ambiguity about which entity to use

**Cons:**
- Loses the "base assay" concept
- Study doesn't directly contain assays (only reverse references)
- Doesn't match ISA-Tab structure

#### Option C: Discriminated Union (Not Supported)

If metaseed supported union types:

```yaml
Study:
  fields:
    - name: assays
      type: list
      items:
        oneOf: [Assay, NMRAssay, LCMSAssay, GCMSAssay]
```

**Pros:**
- Single list, multiple types
- Matches ISA-Tab conceptually

**Cons:**
- Not currently supported in metaseed
- Complex validation logic
- Pydantic discriminated unions add complexity

#### Option D: Generic Assay with Type Field

Use only the generic `Assay` with an `assay_type` discriminator and optional fields:

```yaml
Assay:
  fields:
    - name: assay_type
      type: string
      constraints:
        enum: [nmr, lcms, gcms]

    # Common fields
    - name: file_name
    - name: measurement_type

    # NMR fields (optional, used when assay_type=nmr)
    - name: pulse_sequence
      required: false
    - name: magnetic_field_strength
      required: false

    # LC-MS fields (optional, used when assay_type=lcms)
    - name: column_type
      required: false
    - name: ionization_mode
      required: false
```

**Pros:**
- Single entity, matches ISA-Tab
- No inheritance needed
- Works with current metaseed

**Cons:**
- Large entity with many optional fields
- No compile-time enforcement of which fields apply to which type
- Validation rules needed for field dependencies

### Decision: Option D (Merged Entity with Discriminator)

After evaluation, **Option D** was implemented because:

1. Keeps a single `Assay` entity that other entities can reference
2. `RawSpectralData` and `MetaboliteAssignment` can point to `Assay.file_name`
3. Simpler graph visualization (Study → Assay → data files)
4. No orphaned entities

### Implementation

Single `Assay` entity with `assay_type` discriminator:

```yaml
Assay:
  fields:
    # Common fields
    - name: file_name
    - name: study_id
      reference: Study.identifier
    - name: assay_type
      constraints:
        enum: [nmr, lcms, gcms]
    - name: measurement_type
    - name: technology_type

    # NMR-specific (optional, used when assay_type=nmr)
    - name: nmr_instrument
    - name: pulse_sequence
    - name: magnetic_field_strength
    - name: acquisition_nucleus

    # MS-specific (optional, used when assay_type=lcms or gcms)
    - name: ms_instrument
    - name: ionization_mode
    - name: mass_analyzer

    # LC-specific (optional, used when assay_type=lcms)
    - name: chromatography_instrument
    - name: column_type

    # GC-specific (optional, used when assay_type=gcms)
    - name: gc_instrument
    - name: derivatization_method

    # Nested data
    - name: raw_spectral_data_files
      items: RawSpectralData
    - name: metabolite_assignments
      items: MetaboliteAssignment
```

Study references assays directly:

```yaml
Study:
  fields:
    - name: assays
      type: list
      items: Assay
```

## The Polymorphism Problem

This design decision reveals a **general problem with flat entity models**: how to handle type hierarchies without inheritance.

### The Challenge

Different modeling paradigms handle this differently:

| Paradigm | Solution |
|----------|----------|
| Relational DB | Table inheritance or discriminator columns |
| OOP | Class inheritance |
| JSON Schema | `oneOf`/`anyOf` with discriminator |
| Pydantic | Discriminated unions |
| Metaseed specs | ? |

### Current Limitations

The merged `Assay` approach works but has drawbacks:

1. **No compile-time type safety** - Nothing prevents setting `pulse_sequence` on a GC-MS assay
2. **Large entities** - 31 fields, most optional for any given assay type
3. **Documentation burden** - Must document which fields apply to which type
4. **Validation gaps** - Can't enforce "if type=nmr then require pulse_sequence"

### Potential Spec-Level Solutions

**1. Conditional field requirements (validation rules):**

```yaml
validation_rules:
  - name: nmr_requires_pulse_sequence
    when: assay_type == "nmr"
    require: [pulse_sequence, magnetic_field_strength, acquisition_nucleus]

  - name: lcms_requires_ms_fields
    when: assay_type == "lcms"
    require: [ms_instrument, ionization_mode, chromatography_instrument]
```

**2. Field groups with conditional inclusion:**

```yaml
field_groups:
  nmr_fields:
    - name: pulse_sequence
      required: true
    - name: magnetic_field_strength
      required: true

Assay:
  include_when:
    - condition: assay_type == "nmr"
      groups: [nmr_fields]
```

**3. Discriminated entity variants (new syntax):**

```yaml
Assay:
  discriminator: assay_type
  common_fields:
    - name: file_name
    - name: study_id
  variants:
    nmr:
      fields:
        - name: pulse_sequence
          required: true
    lcms:
      fields:
        - name: chromatography_instrument
          required: true
```

**4. Entity composition (current workaround):**

Define technology-specific detail entities and reference them:

```yaml
Assay:
  fields:
    - name: nmr_details
      type: entity
      items: NMRDetails
      required: false
    - name: lcms_details
      type: entity
      items: LCMSDetails
      required: false
```

### Recommendation for Metaseed

Consider implementing **Option 1 (Conditional validation rules)** as a near-term solution:

- Minimal spec syntax changes
- Leverages existing validation infrastructure
- Provides runtime enforcement without model complexity

Long-term, **Option 3 (Discriminated variants)** would provide the cleanest developer experience but requires significant spec parser changes.

## Other Design Decisions

### Sample Flow

ISA-Tab models sample processing as: Source → Sample → Extract → (assay)

MetaboLights follows this, but the metaseed profile simplifies it to direct references rather than process chains.

### Metabolite Identification

The `MetaboliteAssignment` entity captures identified metabolites with:
- Chemical identifiers (ChEBI, InChI, SMILES)
- Spectral coordinates (retention time, m/z)
- MSI confidence level (1-4)

This is linked to assays rather than studies, reflecting that identifications come from specific analytical runs.

### Controlled Vocabularies

MetaboLights uses several ontologies:
- ChEBI for metabolite identifiers
- PSI-MS for mass spectrometry terms
- NCBI Taxonomy for organisms
- Unit Ontology for measurements

These are validated via the `ontology_term` field property and the OntologyService.
