# Specification

This section is the normative reference for metaseed: what the system is, the
contracts it upholds, and what a consumer may rely on across releases. It
complements the task-oriented [Guides](../guides/spec-builder.md) and the
component-level [Architecture](../architecture/overview.md) notes — those explain
*how* to use and *how it works*; this section defines *what is guaranteed*.

## Documents

| Document | Purpose |
|----------|---------|
| [System Specification](system-specification.md) | Purpose and scope, terminology, the data model, and the validation and serialization guarantees. |
| [Public API Contract](api-contract.md) | The stable public surface, the versioning and compatibility policy, and what consumers may depend on. |
| [Specification Language](../api/schema-specs.md) | The normative reference for the YAML profile files that drive the models (field types, markers, constraints, relationships, rules). |

## Normative language

The word **MUST** marks a guarantee the library upholds and a consumer may rely
on. **SHOULD** marks a strong recommendation with known, narrow exceptions.
**MAY** marks optional behavior. Anything not stated as MUST is not a stability
guarantee and may change between releases.

## Status

metaseed is pre-1.0 software. The compatibility policy in the
[Public API Contract](api-contract.md#versioning-and-compatibility) describes
precisely what that means for the guarantees below.
