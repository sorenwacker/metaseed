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

### Recommendation

For MetaboLights, **Option A (Separate Lists)** is recommended because:

1. Most studies use a single technology (NMR or MS, rarely both)
2. Type safety prevents mixing incompatible assay configurations
3. Graph visualization clearly shows Study → specific assay relationships
4. Each assay type is self-documenting with only relevant fields

### Implementation

Update Study entity:

```yaml
Study:
  fields:
    # Remove generic assays field
    # - name: assays
    #   items: Assay

    # Add technology-specific lists
    - name: nmr_assays
      type: list
      items: NMRAssay
      required: false
      description: NMR spectroscopy assays in this study.

    - name: lcms_assays
      type: list
      items: LCMSAssay
      required: false
      description: LC-MS assays in this study.

    - name: gcms_assays
      type: list
      items: GCMSAssay
      required: false
      description: GC-MS assays in this study.
```

Keep the generic `Assay` entity for cases where technology-agnostic assay metadata is needed, but don't link it from Study.

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
