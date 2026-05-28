# Architecture Overview

Schema-driven architecture where YAML specs define metadata structure, and Pydantic models are generated at runtime.

```mermaid
graph TB
    subgraph Interfaces
        CLI[CLI - Typer]
        Web[Web - HTMX]
        API[REST API - FastAPI]
        MCP[MCP Server]
    end

    subgraph PublicAPI["Public API"]
        Client[MetaseedClient]
    end

    subgraph Core["Core Layer"]
        Factory[Model Factory]
        Validators
        Facade[ProfileFacade]
        Repos[Entity Repository]
    end

    subgraph Data["Data Layer"]
        Specs[Schema Specs - YAML]
        Storage
    end

    subgraph Agent["Agent Layer"]
        Parsers[File Parsers]
        Mapping[Column Mapping]
        Extract[Extraction Context]
    end

    Interfaces --> PublicAPI
    PublicAPI --> Core
    Core --> Data
    MCP --> Agent
    Agent --> Core
```

## Components

| Component | Responsibility |
|-----------|----------------|
| **[MetaseedClient](../api/client.md)** | Clean public API for programmatic access |
| **Schema Specs** | YAML files defining fields, types, and ontology references |
| **Model Factory** | Generates Pydantic models from specs at runtime |
| **Validators** | Cross-field validation, ontology checks, referential integrity |
| **ProfileFacade** | Fluent API for entity discovery and creation (internal) |
| **[Entity Repository](entity-repository.md)** | Unified API for entity CRUD with pluggable backends |
| **[Metadata Agent](metadata-agent.md)** | AI-assisted metadata extraction via MCP |
| **CLI** | Command-line interface (Typer) |
| **Web UI** | Visual editor (HTMX) |
| **REST API** | HTTP endpoints (FastAPI) |

## Design Principles

1. **Schema-first**: Metadata structure defined in YAML specs
2. **Ontology-backed**: References to PPEO, ISA, PROV-O ontologies
3. **Validation-focused**: Multiple validation layers
4. **Interface-agnostic**: Core logic separated from interfaces
5. **Clean API boundary**: Public API decoupled from internal implementation

## Public API Design

The `MetaseedClient` class provides a clean public API boundary that:

- Wraps `ProfileFacade` to hide internal implementation details
- Returns immutable domain objects (`Entity`, `EntityNode`, `FieldInfo`) instead of internal types
- Uses a dedicated exception hierarchy (`MetaseedError` and subclasses)
- Supports both installed profiles and custom spec dictionaries

```python
from metaseed import MetaseedClient

client = MetaseedClient("miappe", "1.2")
inv = client.create_entity("Investigation", {"unique_id": "INV-001", "title": "My Study"})
result = client.validate()
```

For interactive use (Jupyter notebooks), the `ProfileFacade` convenience functions remain available:

```python
from metaseed import miappe
m = miappe()
m.Investigation.help()  # Tab completion and help
```

## Dependency Injection

The codebase uses dependency injection via `ContextVar` for request-scoped state, avoiding module-level globals.

### MCPContext

`MCPContext` holds dependencies for MCP tools:

```python
from metaseed.agent.mcp.context import MCPContext

context = MCPContext(
    state=app_state,
    get_entity_service=lambda: EntityService(repo),
    dataset_factory=DatasetManagerFactory(),
)
set_context(context)
```

| Field | Type | Description |
|-------|------|-------------|
| `state` | `AppState` | Shared application state |
| `get_entity_service` | `Callable` | Factory for EntityService instances |
| `dataset_factory` | `DatasetManagerFactory` | Manages dataset persistence |

### ProfileContext

`ProfileContext` is an immutable dataclass that encapsulates the `(profile, version)` pair used throughout the codebase. This reduces parameter passing and provides a consistent cache key.

```python
from metaseed.core.context import ProfileContext

ctx = ProfileContext(profile="miappe", version="1.2")
loader.load_profile(ctx=ctx)
loader.load_entity("Investigation", ctx=ctx)
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `profile` | `str` | Profile name (e.g., "miappe", "isa", "darwin-core") |
| `version` | `str` | Version string (e.g., "1.1", "1.0") |
| `cache_key` | `str` | Generated key in format "profile:version" |

The `cache_key` property enables consistent caching across components that operate on profile-version combinations.

## Entity Relationships

Entities are linked through **parent ID reference fields**. Each nested entity includes a reference to its parent, enabling:

- Round-trip Excel export/import
- Flat tabular representation
- Cross-entity validation

### MIAPPE Entity Hierarchy

```
Investigation
├── contacts → Person (investigation_id)
└── studies → Study (investigation_id)
    ├── persons → Person (study_id)
    ├── geographic_location → Location (study_id)
    ├── data_files → DataFile (study_id)
    ├── biological_materials → BiologicalMaterial (study_id)
    ├── observation_units → ObservationUnit (study_id)
    │   ├── samples → Sample (observation_unit_id)
    │   └── factor_values → FactorValue (observation_unit_id)
    ├── observed_variables → ObservedVariable (study_id)
    ├── factors → Factor (study_id)
    ├── events → Event (study_id)
    └── environments → Environment (study_id)
```

### Parent Reference Fields

| Entity | Parent Field | Parent Type |
|--------|--------------|-------------|
| Study | `investigation_id` | Investigation |
| Person | `investigation_id` or `study_id` | Investigation or Study |
| BiologicalMaterial | `study_id` | Study |
| ObservationUnit | `study_id` | Study |
| Sample | `observation_unit_id` | ObservationUnit |
| DataFile | `study_id` | Study |
| Factor | `study_id` | Study |
| FactorValue | `factor_id` | Factor |
| Event | `study_id` | Study |
| Environment | `study_id` | Study |
| Location | `study_id` | Study |

These references are required fields, ensuring every entity can be linked back to its parent for tabular export and validation.
