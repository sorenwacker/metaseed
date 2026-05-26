# Entity Relationships: Nested vs Reference

This document discusses how entity relationships are defined in metaseed profile specifications and how they appear in visualizations.

## Two Relationship Types

### 1. Nested Relationships (Solid Lines)

Nested relationships represent containment - one entity owns/contains another. Defined using `type: list` or `type: entity` with `items`:

```yaml
Study:
  fields:
    - name: samples
      type: list
      items: Sample  # Study contains Samples
```

In the graph: **Study → Sample** (solid line, green)

### 2. Reference Relationships (Dashed Lines)

Reference relationships are pointers from child to parent. Defined using the `reference` property:

```yaml
Experiment:
  fields:
    - name: study_ref
      type: string
      reference: Study.alias  # Points to Study's alias field
```

In the graph: **Experiment → Study** (dashed line, purple)

## When to Use Each

| Use Case | Relationship Type | Example |
|----------|------------------|---------|
| Parent owns children | Nested | Study.samples → Sample |
| Child references parent | Reference | Experiment.study_ref → Study |
| Bidirectional | Both | Study has samples (nested) + Sample has study_ref (reference) |

## The MetaboLights Assay Case

MetaboLights has specialized assay types (`NMRAssay`, `LCMSAssay`, `GCMSAssay`) that needed to connect to `Study`.

Initial problem: These entities had `parent_ref` (for auto-fill behavior) but no `reference` (for graph visualization).

Solution: Add both properties:

```yaml
NMRAssay:
  fields:
    - name: study_id
      type: string
      parent_ref: Study.identifier  # Auto-fill from parent context
      reference: Study.identifier   # Show edge in graph
```

## Property Meanings

| Property | Purpose | Used By |
|----------|---------|---------|
| `items` | Define nested entity type | Model generation, graph edges |
| `reference` | Define reference target | Graph visualization, validation |
| `parent_ref` | Auto-fill from parent | Form UI, nested editing |

## Why Not Inheritance?

Some profiles (like MetaboLights) have entity hierarchies where `NMRAssay` is conceptually a subtype of `Assay`.

Metaseed does not support entity inheritance (`extends`) because:

1. Pydantic model generation becomes complex
2. Field conflicts between parent/child are ambiguous
3. Validation rules become harder to reason about

Instead, use composition:
- Define shared fields in each entity
- Use reference fields to link related entities
- Use validation rules for cross-entity constraints

## Graph Visualization Logic

The visualizer (`src/metaseed/specs/merge/visualizer.py`) creates edges by:

1. **Nested edges**: Fields with `type: entity` or `type: list` where `items` is an entity name
2. **Reference edges**: Fields with `reference` property pointing to `Entity.field`

```python
# Nested relationship detection
if spec.type.value == "entity" or (spec.type.value == "list" and spec.items):
    target = spec.items

# Reference relationship detection
if spec.reference:
    ref_target = spec.reference.split(".")[0]  # "Study.alias" → "Study"
```
