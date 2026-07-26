# System Specification

## Purpose

Metaseed creates, edits, validates, and serializes structured research metadata
against a chosen standard. The set of supported standards is open: each is
described by a YAML *profile* rather than hard-coded, so one codebase serves
MIAPPE, ISA, Darwin Core, DiSSCo, ENA, JERM, PRIDE, and MetaboLights, and a new
standard is added by writing a profile, not by changing the engine.

## Scope

This specification covers the metaseed library: the profile model, the runtime
model generation, the two-layer validation, and the serialization guarantees. It
does **not** cover the web application (metaseed-hub) or the CLI, which are
consumers of the library; nor does it cover the correctness of any individual
profile's mapping to its upstream submission system, which each adapter documents
separately.

## Terminology

| Term | Definition |
|------|-----------|
| **Profile** | A named, versioned YAML file describing one standard: its entity types, their fields, the root entity, and cross-entity rules. |
| **Entity type** | A class of object within a profile (e.g. `Investigation`, `Study`, `Sample`). |
| **Field** | A typed, named attribute of an entity type, optionally carrying an ontology term, constraints, and markers. |
| **Entity** | An instance of an entity type holding user data. |
| **Root entity** | The single entity type that sits at the top of a profile's hierarchy. |
| **Dataset** | A collection of entities for one profile and version, forming a tree. |
| **Facade** | `ProfileFacade`, the in-process store and single source of truth for a dataset's entity graph. |
| **Client** | `MetaseedClient`, the public boundary that wraps the facade and returns immutable domain objects. |

The normative definition of the profile file format — every field type, marker,
constraint, and rule — is the [Specification Language](../api/schema-specs.md)
reference. This document specifies the *behavior* built on top of it.

## The data model

A profile defines a directed hierarchy of entity types rooted at one
`root_entity`. At runtime metaseed generates one Pydantic model per entity type
from the profile, so field types, requiredness, and constraints are enforced by
model construction.

A dataset is a tree of entities:

- **Parent–child** edges come from a nested-entity field on the parent, or from a
  child carrying a reference field that names its parent.
- **Entity references** link entities by identifier without nesting.
- **One-to-one embedding** folds a single related entity inline.

The engine MUST resolve these relationships into a single tree reachable from the
roots. The edge cases of that resolution — a reference to a missing parent, a
vanished backing file — are specified in
[ADR 002](../architecture/decisions/002-edge-case-behavior.md) and are covered by
tests: a dangling parent reference MUST NOT cause the entity to disappear.

## Runtime model generation

Given a profile and version, metaseed generates validated Pydantic models:

```python
from metaseed import get_model

Investigation = get_model("Investigation")
inv = Investigation(unique_id="INV-001", title="Drought Study")
```

Model generation MUST be deterministic: the same profile and version always
produce the same model surface (field names, types, requiredness).

## Validation

Validation has two layers, and both run before a dataset is considered valid.

1. **Field constraints (model layer).** Type, requiredness, and per-field
   constraints (`pattern`, `min_length`/`max_length`, `minimum`/`maximum`,
   `min_items`/`max_items`, `enum`) are enforced when an entity model is
   constructed. A validator MUST check every constraint it advertises: list
   cardinality and zero-valued length bounds are enforced, not silently skipped
   (see [ADR 002](../architecture/decisions/002-edge-case-behavior.md)).
2. **Validation rules (engine layer).** Cross-field and cross-entity rules
   (uniqueness, coordinate pairs, conditional requirements, reference integrity)
   run over the assembled dataset.

Validation reports results as structured issues rather than exceptions:

```python
from metaseed import MetaseedClient

client = MetaseedClient("miappe", "1.2")
client.create_entity("Investigation", {"unique_id": "INV-001", "title": "S"})
result = client.validate()
```

`validate()` MUST return a `ValidationResult` whose issues each identify the
offending field or rule; it MUST NOT raise for ordinary validation failures.

The distinction between the two layers, and when to use a field constraint versus
a rule, is detailed in
[Specification Language › Validation](../api/schema-specs.md#validation-field-constraints-vs-rules).

## Serialization

A dataset serializes to a hierarchical (tree) structure suitable for JSON, and to
YAML via the storage helpers. Serialization MUST round-trip: loading a serialized
dataset back into a facade MUST reproduce the same entity graph (this round-trip
is a target gate; see the [development notes](../development/testing.md)).

Reads MUST NOT expose mutable internal state: accessors return copies, so a
caller cannot corrupt the store by mutating a returned object
([ADR 002](../architecture/decisions/002-edge-case-behavior.md)).

## Storage and ports

The core is pure and depends on injectable ports rather than a fixed backend. The
default adapters (`JsonStorage`, `YamlStorage`, the in-memory and file entity
repositories) cover single-user and file-based use; a consumer such as
metaseed-hub injects its own database-backed adapters without forking the core.
The storage contract is documented in [Storage](../api/storage.md).

## Supported standards

Standards ship as installed profiles; repository adapters that import from or
export to an upstream system are optional extras (`metaseed[ena]`,
`metaseed[pride]`, `metaseed[metabolights]`, `metaseed[brapi]`, `metaseed[seek]`,
`metaseed[dcat]`). An adapter is a pure mapper/writer and MUST import without
pulling in the web framework. Per-adapter scope and caveats are documented under
[Architecture › Integration Adapters](../architecture/integration-adapters.md).
