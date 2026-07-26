# Public API Contract

This document defines metaseed's public surface — the symbols a consumer may
import and rely on — and the policy governing how that surface changes across
releases.

## What is public

The public API is exactly the set of names exported from the top-level
`metaseed` package (its `__all__`). Anything reachable only through a submodule,
and any name prefixed with an underscore, is an implementation detail and is
**not** covered by the guarantees below.

```python
import metaseed

print(metaseed.__all__)
```

### Stable surface

| Symbol | Kind | Contract |
|--------|------|----------|
| `MetaseedClient` | class | The primary boundary: create/edit/validate/serialize a dataset for one profile. |
| `ProfileFacade` | class | In-process entity store; the interactive/notebook entry point. |
| `get_model` | function | Return the generated Pydantic model for an entity type. |
| `SpecLoader` | class | Load and cache profile specifications. |
| `validate` | function | Validate a dataset and return a `ValidationResult`. |
| `Entity`, `EntityNode`, `EntitySchema`, `FieldInfo` | classes | Immutable domain objects returned by the client. |
| `ValidationResult`, `ValidationIssue` | classes | Structured validation output. |
| `JsonStorage`, `YamlStorage` | classes | Default storage adapters. |
| `MetaseedError`, `EntityNotFoundError`, `EntityTypeNotFoundError`, `ProfileNotFoundError` | exceptions | The exception hierarchy; all library errors derive from `MetaseedError`. |
| `list_profiles` | function | Discover installed profile names. |
| `miappe`, `miappe_htp`, `isa`, `darwin_core`, `dissco`, `ena`, `jerm`, `pride`, `metabolights` | functions | Convenience constructors for a profile facade. |
| `__version__` | attribute | The installed version string. |

Every symbol above resolves from the top-level package:

```python
from metaseed import (
    MetaseedClient,
    ProfileFacade,
    SpecLoader,
    get_model,
    validate,
    Entity,
    EntityNode,
    EntitySchema,
    FieldInfo,
    ValidationResult,
    ValidationIssue,
    JsonStorage,
    YamlStorage,
    MetaseedError,
    EntityNotFoundError,
    EntityTypeNotFoundError,
    ProfileNotFoundError,
    list_profiles,
)
```

### The client contract

`MetaseedClient` MUST:

- return immutable domain objects (`Entity`, `EntityNode`, `FieldInfo`) rather
  than internal types, so callers cannot mutate engine state through a result;
- raise only exceptions derived from `MetaseedError` for its own error
  conditions; and
- report ordinary validation failures as a `ValidationResult`, not as an
  exception.

### Not public

- Any submodule path (`metaseed.facade.store`, `metaseed.repositories.file`, …).
  These move and change without notice; import from the top-level package.
- Underscore-prefixed names and members.
- The adapter internals. The supported entry point for each adapter is its
  documented `import_accession` / export function under the corresponding extra,
  not the modules beneath it.

## Extras

The core installs with no web or network dependencies. Adapters are optional
extras and MUST import without pulling in the web framework:

| Extra | Adds |
|-------|------|
| `metaseed[ena]` | ENA import/export |
| `metaseed[brapi]` | BrAPI v2 import/export |
| `metaseed[pride]` | PRIDE / ProteomeXchange import/export |
| `metaseed[metabolights]` | MetaboLights import/export |
| `metaseed[seek]` | FAIRDOM-SEEK provisioning/export |
| `metaseed[dcat]` | DCAT catalog export |
| `metaseed[docs]`, `metaseed[dev]` | Documentation and development tooling |

Importing an adapter without its extra MUST fail with a clear message naming the
extra to install, not an opaque `ModuleNotFoundError`.

## Versioning and compatibility

metaseed follows Semantic Versioning. The version is derived from the Git tag at
build time (`hatch-vcs`); a `v*` tag is the single source of release truth and
publishes the release to PyPI.

**Pre-1.0 status.** While the version is `0.y.z`, the public surface is still
settling: a minor bump (`0.y`) MAY include a breaking change to the public API.
Such changes MUST be recorded in the [changelog](https://github.com/sorenwacker/metaseed/blob/main/CHANGELOG.md).
Patch bumps (`0.y.z`) MUST NOT break the public API.

After 1.0, breaking changes to the public API will be confined to major bumps.

Requires Python 3.11 or newer.

## Deprecation policy

When a public symbol is to be removed, it SHOULD first be marked deprecated in a
release — kept working, documented as deprecated in the changelog — before removal
in a later release. Because the project is pre-1.0, a deprecation-then-removal
cycle MAY span minor versions rather than requiring a major bump.

## Consumer contract

metaseed-hub is a first-class downstream consumer and depends only on the public
surface defined here. Changes that remove or rename a public symbol MUST be
checked against metaseed-hub before release. A public-API surface snapshot test
guarding this contract is a planned gate (issue
[#68](https://github.com/sorenwacker/metaseed/issues/68)).
