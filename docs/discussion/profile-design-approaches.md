# Profile Design Approaches

When creating profiles for scientific databases, several design decisions affect usability, maintainability, and semantic accuracy.

## Combining Profiles: Naive vs Elaborate Merge

When experiments span multiple domains (e.g., phenotyping + proteomics), users need combined profiles.

### Option 1: Naive Merge (Duplication)

Simply include all entities from both profiles, accepting duplication:

```yaml
# Combined profile with duplicated entities
entities:
  # From MIAPPE
  Investigation:
    fields: [...]
  Study:
    fields: [...]

  # From ISA (duplicates Investigation, Study)
  Investigation:  # Conflict!
    fields: [...]
```

**Pros:**
- Simple to implement
- Each profile remains intact
- No semantic interpretation needed

**Cons:**
- Name conflicts require resolution
- Redundant storage
- Users must understand which entity to use when

### Option 2: Intelligent Merge

Analyze profiles semantically and merge compatible entities:

```yaml
# Merged Investigation combining both
Investigation:
  fields:
    - name: identifier      # From both
    - name: title           # From both
    - name: description     # From both
    - name: ontology_sources # ISA-specific
    - name: location        # MIAPPE-specific
```

**Pros:**
- Single coherent model
- Reduced redundancy
- Cross-domain experiments fit naturally

**Cons:**
- Complex merge logic
- Semantic decisions may be wrong
- Field conflicts need resolution strategy

### Current Implementation

Metaseed supports both via the `compare` and `merge` CLI commands:

```bash
# Compare to see differences
metaseed compare miappe/1.1 isa/1.0

# Merge with strategy
metaseed merge miappe/1.1 isa/1.0 --strategy most-restrictive
```

Merge strategies:
- `first-wins`: Keep first profile's definition on conflict
- `last-wins`: Keep last profile's definition
- `most-restrictive`: Use stricter validation
- `least-restrictive`: Use looser validation

## Repository-Specific Profiles: Copy vs Adapt

When creating profiles for repositories like MetaboLights, PRIDE, or ENA, a key question is how closely to follow the original schema.

### MetaboLights Case Study

MetaboLights uses ISA-Tab format with assay type specializations:
- `Assay` (base)
- `NMRAssay` (NMR-specific fields)
- `LCMSAssay` (LC-MS-specific fields)
- `GCMSAssay` (GC-MS-specific fields)

The original ISA-Tab handles this via naming conventions in assay files, not entity inheritance.

**Question:** Should metaseed support entity inheritance (`extends`)?

### Arguments Against Inheritance

1. **Complexity**: Pydantic model generation becomes significantly more complex
2. **Field conflicts**: What happens when child overrides parent field with different type?
3. **Validation ambiguity**: Do parent validation rules apply to children?
4. **Graph visualization**: How to show inheritance vs composition relationships?

### Alternative: Composition

Instead of inheritance, use composition and shared fields:

```yaml
# Each assay type is standalone
NMRAssay:
  fields:
    # Shared assay fields (duplicated but explicit)
    - name: file_name
    - name: study_id
      reference: Study.identifier
    - name: measurement_type

    # NMR-specific fields
    - name: pulse_sequence
    - name: magnetic_field_strength
```

**Pros:**
- Simple model
- Each entity is self-contained
- Clear what fields exist

**Cons:**
- Field duplication across similar entities
- Changes to "base" fields require updating all variants

### Recommendation

For repository profiles:

1. **Don't blindly copy** - Adapt to metaseed's model
2. **Prefer composition** over inheritance
3. **Use reference fields** to establish relationships
4. **Document deviations** from original schema

## Open Questions

1. Should metaseed support a `fields_from` directive to include fields from another entity without inheritance?

```yaml
NMRAssay:
  fields_from: Assay  # Include all Assay fields
  fields:
    - name: pulse_sequence  # Additional NMR-specific fields
```

2. Should field groups be supported for reuse?

```yaml
field_groups:
  common_assay_fields:
    - name: file_name
    - name: study_id
    - name: measurement_type

NMRAssay:
  include_groups: [common_assay_fields]
  fields:
    - name: pulse_sequence
```

3. Is there value in maintaining strict 1:1 mapping with repository schemas, or should metaseed profiles be optimized for the metaseed data model?
